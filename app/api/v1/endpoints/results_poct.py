"""Saisie POCT (Point-of-Care Testing) — Flux 2.

Deux entrées coexistent, sur le même socle de bornes cliniques
(``app.services.validation.poct_reference``) :

- ``POST /results/precis-expert`` : contrat historique, figé sur les 5
  paramètres de l'appareil (conservé pour la rétrocompatibilité de l'UI) ;
- ``POST /results/poct-batch`` : contrat **générique** device-agnostique,
  saisie groupée et simultanée de N analytes en une seule transaction.
"""

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, Patient, Result, Sample, User
from app.schemas.poct import POCTBatchResponse, POCTBatchSubmission
from app.schemas.precis_expert import PrecisExpertManualInput
from app.services.audit import log_audit_event
from app.services.inventory import InsufficientStockError, consume_reagents_for_result
from app.services.patient_access import can_access_patient
from app.services.validation.poct_reference import POCT_ANALYTES, build_poct_point
from app.services.validation.precis_expert import PrecisExpertValidator

router = APIRouter(prefix="/results")


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _resolve_sample_and_patient(
    db: Session, *, barcode: str, current_user: User
) -> tuple[Sample, Patient]:
    """Résout l'échantillon et son patient, avec contrôle de périmètre."""
    sample = db.query(Sample).filter(Sample.barcode == barcode).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Erreur pre-analytique: code-barres {barcode} inconnu.",
        )
    patient = db.query(Patient).filter(Patient.id == sample.patient_id).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"L'echantillon {sample.barcode} n'est lie a aucun patient valide.",
        )
    if not can_access_patient(current_user, patient):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : dossier hors de votre périmètre.",
        )
    return sample, patient


@router.post("/precis-expert", status_code=status.HTTP_201_CREATED)
def submit_precis_expert_results(
    payload: PrecisExpertManualInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    sample, patient = _resolve_sample_and_patient(
        db, barcode=payload.sample_barcode, current_user=current_user
    )

    analysis_date = utcnow_naive()
    age_in_years = (
        analysis_date.year
        - patient.birth_date.year
        - (
            (analysis_date.month, analysis_date.day)
            < (patient.birth_date.month, patient.birth_date.day)
        )
    )

    validator = PrecisExpertValidator(payload, age_in_years, patient.sex, current_user.id)
    validated_jsonb, is_panic = validator.validate_all()

    equipment = (
        db.query(Equipment)
        .filter(
            Equipment.serial_number == payload.equipment_serial,
            Equipment.name == "Precis Expert",
        )
        .first()
    )
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Appareil Precis Expert non enregistre: {payload.equipment_serial}.",
        )

    new_result = Result(
        sample_id=sample.id,
        equipment_id=equipment.id,
        analysis_date=analysis_date,
        data_points=validated_jsonb.model_dump(),
        validator_id=current_user.id,
        is_validated=True,
        is_critical=is_panic,
    )
    sample.status = "Termine"
    db.add(new_result)
    db.flush()
    try:
        consume_reagents_for_result(
            db,
            result=new_result,
            user=current_user,
            source="result.precis_expert.create",
        )
    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stock reactif insuffisant pour valider ce resultat.",
                "items": [item.__dict__ for item in exc.items],
            },
        ) from exc
    log_audit_event(
        db,
        user=current_user,
        event_type="result.precis_expert.create",
        entity_type="result",
        entity_id=str(new_result.id),
        payload={
            "sample_barcode": sample.barcode,
            "equipment_serial": payload.equipment_serial,
            "is_critical": is_panic,
        },
    )
    db.commit()
    db.refresh(new_result)

    return {
        "status": "success",
        "message": f"Resultats Precis Expert inseres pour {sample.barcode}.",
        "result_id": new_result.id,
        "is_critical": is_panic,
    }


@router.post("/poct-batch", status_code=status.HTTP_201_CREATED, response_model=POCTBatchResponse)
def submit_poct_batch(
    payload: POCTBatchSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Enregistre en une transaction un lot d'analytes POCT d'un échantillon."""
    sample, patient = _resolve_sample_and_patient(
        db, barcode=payload.sample_barcode, current_user=current_user
    )

    equipment = (
        db.query(Equipment)
        .filter(
            Equipment.serial_number == payload.device_serial,
            Equipment.name == payload.device_model,
        )
        .first()
    )
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Appareil POCT non enregistre: {payload.device_model} / {payload.device_serial}."
            ),
        )

    analysis_date = utcnow_naive()
    if payload.measured_at is not None:
        measured = payload.measured_at
        analysis_date = measured.replace(tzinfo=None) if measured.tzinfo else measured

    # Validation groupée : chaque analyte est confronté à son intervalle de
    # référence (différencié par sexe le cas échéant) issu du catalogue POCT.
    data_points: dict[str, Any] = {}
    analytes: list[dict[str, Any]] = []
    is_critical = False
    for item in payload.items:
        point = build_poct_point(item.code, item.value, item.unit, patient.sex)
        if point.is_critical:
            is_critical = True
        data_points[item.code] = point.model_dump()
        analytes.append(
            {"code": item.code, "label": POCT_ANALYTES[item.code].label, "point": point}
        )

    data_points.update(
        {
            "device_model": payload.device_model,
            "device_serial": payload.device_serial,
            "manual_entry_by": current_user.id,
            "entry_timestamp": analysis_date.isoformat(),
        }
    )

    new_result = Result(
        sample_id=sample.id,
        equipment_id=equipment.id,
        analysis_date=analysis_date,
        data_points=data_points,
        result_type="poct",
        validator_id=current_user.id,
        is_validated=True,
        is_critical=is_critical,
    )
    sample.status = "Termine"
    db.add(new_result)
    db.flush()
    try:
        consume_reagents_for_result(
            db,
            result=new_result,
            user=current_user,
            source="result.poct_batch.create",
        )
    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stock reactif insuffisant pour valider ce resultat.",
                "items": [item.__dict__ for item in exc.items],
            },
        ) from exc
    log_audit_event(
        db,
        user=current_user,
        event_type="result.poct_batch.create",
        entity_type="result",
        entity_id=str(new_result.id),
        payload={
            "sample_barcode": sample.barcode,
            "device_model": payload.device_model,
            "device_serial": payload.device_serial,
            "analytes": [item.code for item in payload.items],
            "is_critical": is_critical,
        },
    )
    db.commit()
    db.refresh(new_result)

    return {
        "status": "success",
        "message": (f"{len(payload.items)} analyte(s) POCT enregistre(s) pour {sample.barcode}."),
        "result_id": new_result.id,
        "is_critical": is_critical,
        "analytes": analytes,
    }

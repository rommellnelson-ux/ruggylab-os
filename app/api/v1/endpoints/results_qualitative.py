"""Saisie des résultats qualitatifs de paillasse (Flux 3).

Parasitologie / cytologie / frottis : résultats non chiffrés saisis au cockpit
de microscopie. Le corps métier (``findings``) est stocké dans le JSONB
``Result.data_points`` ; le discriminateur ``Result.result_type`` vaut
``"qualitative"``. La clé ``image_url`` réutilise le chemin réservé par le
composant de capture microscope existant (/imaging/capture-microscope).
"""

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Patient, Result, User
from app.schemas.qualitative import QualitativeResultResponse, QualitativeResultSubmission
from app.services.audit import log_audit_event
from app.services.patient_access import can_access_patient
from app.services.sample_workflow import (
    CancelledSampleError,
    ensure_sample_processable,
    lock_sample_by_barcode,
)

router = APIRouter(prefix="/results/qualitative")


def _utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QualitativeResultResponse)
def submit_qualitative_result(
    payload: QualitativeResultSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    sample = lock_sample_by_barcode(db, payload.sample_barcode)
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Erreur pre-analytique: code-barres {payload.sample_barcode} inconnu.",
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
    try:
        ensure_sample_processable(sample)
    except CancelledSampleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    findings = payload.findings
    # Une parasitologie positive est une valeur d'alerte clinique (p. ex.
    # Plasmodium à l'examen direct) : on la marque critique pour la prise en
    # charge, comme les valeurs paniques chiffrées.
    is_critical = payload.category == "parasitology" and not findings.is_negative

    data_points = {
        "category": payload.category,
        "is_negative": findings.is_negative,
        "observations": [obs.model_dump() for obs in findings.observations],
        "comment": findings.comment,
        "entered_by": current_user.id,
        "entry_timestamp": _utcnow_naive().isoformat(),
    }

    new_result = Result(
        sample_id=sample.id,
        analysis_date=_utcnow_naive(),
        data_points=data_points,
        result_type="qualitative",
        exam_code=payload.exam_code,
        image_url=payload.image_url,
        validator_id=current_user.id,
        is_validated=True,
        is_critical=is_critical,
    )
    sample.status = "Termine"
    db.add(new_result)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="result.qualitative.create",
        entity_type="result",
        entity_id=str(new_result.id),
        payload={
            "sample_barcode": sample.barcode,
            "category": payload.category,
            "is_negative": findings.is_negative,
            "observation_count": len(findings.observations),
            "is_critical": is_critical,
        },
    )
    db.commit()
    db.refresh(new_result)

    return {
        "status": "success",
        "message": f"Resultat qualitatif ({payload.category}) enregistre pour {sample.barcode}.",
        "result_id": new_result.id,
        "is_critical": is_critical,
        "image_url": new_result.image_url,
    }

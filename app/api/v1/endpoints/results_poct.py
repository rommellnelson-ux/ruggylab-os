import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, Patient, Result, Sample
from app.schemas.precis_expert import PrecisExpertManualInput
from app.services.audit import log_audit_event
from app.services.validation.precis_expert import PrecisExpertValidator

router = APIRouter(prefix="/results/precis-expert")


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_precis_expert_results(
    payload: PrecisExpertManualInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict[str, Any]:
    sample = db.query(Sample).filter(Sample.barcode == payload.sample_barcode).first()
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

    analysis_date = utcnow_naive()
    age_in_years = (
        analysis_date.year
        - patient.birth_date.year
        - (
            (analysis_date.month, analysis_date.day)
            < (patient.birth_date.month, patient.birth_date.day)
        )
    )

    validator = PrecisExpertValidator(
        payload, age_in_years, patient.sex, current_user.id
    )
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

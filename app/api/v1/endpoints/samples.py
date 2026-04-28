from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Patient, Sample, User
from app.schemas.sample import SampleCreate, SampleRead


router = APIRouter(prefix="/samples")


@router.get("", response_model=list[SampleRead])
def list_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> list[Sample]:
    del current_user
    return db.query(Sample).order_by(Sample.id.desc()).all()


@router.post("", response_model=SampleRead, status_code=status.HTTP_201_CREATED)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Sample:
    del current_user
    existing = db.query(Sample).filter(Sample.barcode == payload.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Echantillon déjà existant pour le code-barres {payload.barcode}.",
        )

    if payload.patient_id is not None:
        patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient introuvable pour l'identifiant {payload.patient_id}.",
            )

    sample_data = payload.model_dump(exclude_none=True)
    sample = Sample(**sample_data)
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Patient, User
from app.schemas.pagination import PaginationMeta, PatientListResponse
from app.schemas.patient import PatientCreate, PatientRead


router = APIRouter(prefix="/patients")


@router.get("", response_model=PatientListResponse)
def list_patients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1),
) -> PatientListResponse:
    del current_user
    query = db.query(Patient)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Patient.ipp_unique_id.ilike(search),
                Patient.first_name.ilike(search),
                Patient.last_name.ilike(search),
                Patient.rank.ilike(search),
            )
        )

    total = query.with_entities(func.count(Patient.id)).scalar() or 0
    items = query.order_by(Patient.id.desc()).offset(skip).limit(limit).all()
    return PatientListResponse(items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit))


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> Patient:
    del current_user
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable.")
    return patient


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Patient:
    del current_user
    existing = db.query(Patient).filter(Patient.ipp_unique_id == payload.ipp_unique_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient deja existant pour l'IPP {payload.ipp_unique_id}.",
        )

    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import Patient, User
from app.schemas.pagination import PaginationMeta, PatientListResponse
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate
from app.services.audit import log_audit_event
from app.services.patient_access import apply_patient_scope, can_access_patient, can_access_unit
from app.services.patient_history import build_patient_fhir_bundle, build_patient_history

router = APIRouter(prefix="/patients")


def _get_patient_or_404(db: Session, patient_id: int) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient introuvable.")
    return patient


def _get_accessible_patient_or_error(db: Session, patient_id: int, user: User) -> Patient:
    """404 si inexistant ; 403 (tracé) si hors périmètre RBAC de l'utilisateur."""
    patient = _get_patient_or_404(db, patient_id)
    if not can_access_patient(user, patient):
        log_audit_event(
            db,
            user=user,
            event_type="patient.access.denied",
            entity_type="patient",
            entity_id=str(patient_id),
            payload={"reason": "hors périmètre unité", "user_unit": user.unit},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au dossier hors de votre périmètre.",
        )
    return patient


@router.get("", response_model=PatientListResponse)
def list_patients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1),
) -> PatientListResponse:
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
    # Cloisonnement RBAC : restreindre au périmètre (unité) de l'utilisateur
    query = apply_patient_scope(query, current_user)

    total = query.with_entities(func.count(Patient.id)).scalar() or 0
    items = query.order_by(Patient.id.desc()).offset(skip).limit(limit).all()
    return PatientListResponse(
        items=[PatientRead.model_validate(p) for p in items],
        meta=PaginationMeta.from_counts(total=total, skip=skip, limit=limit),
    )


@router.get("/{patient_id}/history")
def get_patient_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Dossier patient complet : timeline des résultats + tendances par analyte."""
    patient = _get_accessible_patient_or_error(db, patient_id, current_user)
    history = build_patient_history(db, patient)
    # Traçabilité de la consultation du dossier (secret médical / ISO 15189)
    log_audit_event(
        db,
        user=current_user,
        event_type="patient.history.view",
        entity_type="patient",
        entity_id=str(patient_id),
        payload={"ipp": patient.ipp_unique_id},
    )
    db.commit()
    return history


@router.get(
    "/{patient_id}/fhir-bundle",
    summary="Export du dossier patient en Bundle FHIR R4 (DiagnosticReports)",
    responses={200: {"content": {"application/fhir+json": {}}}},
)
def get_patient_fhir_bundle(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONResponse:
    """Regroupe tous les résultats du patient en un Bundle FHIR R4."""
    patient = _get_accessible_patient_or_error(db, patient_id, current_user)
    bundle = build_patient_fhir_bundle(db, patient)
    # Traçabilité de l'export de données patient
    log_audit_event(
        db,
        user=current_user,
        event_type="patient.fhir.export",
        entity_type="patient",
        entity_id=str(patient_id),
        payload={"ipp": patient.ipp_unique_id, "resource_count": bundle.get("total", 0)},
    )
    db.commit()
    return JSONResponse(content=bundle, media_type="application/fhir+json")


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Patient:
    return _get_accessible_patient_or_error(db, patient_id, current_user)


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Patient:
    if not can_access_unit(current_user, payload.unit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Création de patient hors de votre périmètre d'unité.",
        )
    existing = db.query(Patient).filter(Patient.ipp_unique_id == payload.ipp_unique_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient deja existant pour l'IPP {payload.ipp_unique_id}.",
        )

    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="patient.create",
        entity_type="patient",
        entity_id=str(patient.id),
        payload={"unit": patient.unit},
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> Patient:
    """Mise à jour partielle d'un patient, dont l'unité (réservé officier/admin).

    Seuls les champs fournis sont modifiés ; ``unit: null`` retire l'affectation.
    """
    patient = _get_patient_or_404(db, patient_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Aucun champ à mettre à jour."
        )
    for key, value in changes.items():
        setattr(patient, key, value)
    log_audit_event(
        db,
        user=current_user,
        event_type="patient.update",
        entity_type="patient",
        entity_id=str(patient_id),
        payload={"fields": sorted(changes.keys())},
    )
    db.commit()
    db.refresh(patient)
    return patient

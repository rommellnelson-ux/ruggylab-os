import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Patient, Result, Sample, User
from app.schemas.sample import SampleCreate, SampleRead, SampleUpdate
from app.services.audit import log_audit_event
from app.services.patient_access import (
    apply_sample_patient_scope,
    can_access_patient,
    can_access_sample,
)
from app.services.sample_workflow import CANCELLED_SAMPLE_STATUS, lock_sample_by_id

router = APIRouter(prefix="/samples")

_LAB_NUMBER_LOCK_NAMESPACE = 0x524C4E55


def _ensure_sample_access(sample: Sample, user: User) -> None:
    if not can_access_sample(user, sample):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès à l'échantillon hors de votre périmètre.",
        )


def _lock_lab_number_sequence(db: Session, year: int) -> None:
    """Sérialise l'allocation annuelle pendant la transaction PostgreSQL."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(select(func.pg_advisory_xact_lock(_LAB_NUMBER_LOCK_NAMESPACE, year)))


def _next_lab_number(db: Session) -> str:
    """N° de laboratoire lisible, séquence annuelle : AAAA-NNNNNN."""
    year = dt.datetime.now(dt.UTC).year
    prefix = f"{year}-"
    _lock_lab_number_sequence(db, year)
    pattern = re.compile(rf"{year}-(\d{{6}})")
    existing_numbers = (
        db.query(Sample.lab_number).filter(Sample.lab_number.like(f"{prefix}%")).all()
    )
    highest = max(
        (
            int(match.group(1))
            for (value,) in existing_numbers
            if value is not None and (match := pattern.fullmatch(value))
        ),
        default=0,
    )
    if highest >= 999_999:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La séquence des numéros de laboratoire {year} est épuisée.",
        )
    return f"{prefix}{highest + 1:06d}"


@router.get("", response_model=list[SampleRead])
def list_samples(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
) -> list[Sample]:
    query = apply_sample_patient_scope(db.query(Sample), current_user)
    samples: list[Sample] = query.order_by(Sample.id.desc()).all()
    return samples


@router.get("/quality-summary")
def sample_quality_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    """Indicateur qualité pré-analytique : répartition par aspect + taux de non-conformité.

    Le taux d'hémolyse / de non-conformité est un indicateur reconnu de la qualité
    du prélèvement (formation des préleveurs).
    """
    query = apply_sample_patient_scope(
        db.query(Sample.aspect, func.count(Sample.id)),
        current_user,
    )
    rows = query.group_by(Sample.aspect).all()
    by_aspect = {(aspect or "non_renseigne"): count for aspect, count in rows}
    total = sum(by_aspect.values())
    qualified = sum(c for a, c in by_aspect.items() if a not in ("non_renseigne",))
    non_conforming = sum(c for a, c in by_aspect.items() if a not in ("conforme", "non_renseigne"))
    hemolyzed = by_aspect.get("hemolyse", 0)

    def _rate(n: int, d: int) -> float:
        return round(100 * n / d, 1) if d else 0.0

    return {
        "total_samples": total,
        "by_aspect": by_aspect,
        "non_conformity_rate_pct": _rate(non_conforming, qualified),
        "hemolysis_rate_pct": _rate(hemolyzed, qualified),
    }


@router.get("/by-barcode/{barcode}", response_model=SampleRead)
def get_sample_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Sample:
    """Résout un échantillon par son code-barres (saisie/scan en salle)."""
    sample = db.query(Sample).filter(Sample.barcode == barcode).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun échantillon pour le code-barres {barcode}.",
        )
    _ensure_sample_access(sample, current_user)
    return sample


@router.post("", response_model=SampleRead, status_code=status.HTTP_201_CREATED)
def create_sample(
    payload: SampleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Sample:
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
        if not can_access_patient(current_user, patient):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès au dossier patient hors de votre périmètre.",
            )

    sample_data = payload.model_dump(exclude_none=True)
    sample = Sample(**sample_data)
    if not sample.lab_number:
        sample.lab_number = _next_lab_number(db)
    db.add(sample)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="sample.create",
        entity_type="sample",
        entity_id=str(sample.id),
        payload={"patient_id": sample.patient_id, "status": sample.status},
    )
    db.commit()
    db.refresh(sample)
    return sample


@router.patch("/{sample_id}", response_model=SampleRead)
def update_sample(
    sample_id: int,
    payload: SampleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Sample:
    """Partial update — statut (Recu → En cours → Termine / Annule) et/ou aspect."""
    sample = lock_sample_by_id(db, sample_id)
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Echantillon introuvable.",
        )
    _ensure_sample_access(sample, current_user)
    old_status = sample.status
    old_aspect = sample.aspect
    updated_fields: list[str] = []
    if payload.status is not None:
        if sample.status == CANCELLED_SAMPLE_STATUS and payload.status != CANCELLED_SAMPLE_STATUS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Un échantillon annulé ne peut pas être réactivé.",
            )
        if (
            payload.status == CANCELLED_SAMPLE_STATUS
            and sample.status != CANCELLED_SAMPLE_STATUS
            and db.query(Result.id).filter(Result.sample_id == sample.id).first() is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Un échantillon portant déjà un résultat ne peut pas être annulé.",
            )
        sample.status = payload.status
        updated_fields.append("status")
    if payload.aspect is not None:
        sample.aspect = payload.aspect
        updated_fields.append("aspect")
    if updated_fields:
        log_audit_event(
            db,
            user=current_user,
            event_type="sample.update",
            entity_type="sample",
            entity_id=str(sample.id),
            payload={
                "fields": sorted(updated_fields),
                "old_status": old_status,
                "new_status": sample.status,
                "old_aspect": old_aspect,
                "new_aspect": sample.aspect,
            },
        )
    db.commit()
    db.refresh(sample)
    return sample

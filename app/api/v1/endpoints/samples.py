import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import ExamOrder, Patient, Sample, User
from app.schemas.sample import SampleCreate, SampleRead, SampleUpdate

router = APIRouter(prefix="/samples")


def _next_lab_number(db: Session) -> str:
    """N° de laboratoire lisible, séquence annuelle : AAAA-NNNNNN."""
    prefix = f"{dt.datetime.now(dt.UTC).year}-"
    count = (
        db.query(func.count(Sample.id)).filter(Sample.lab_number.like(f"{prefix}%")).scalar() or 0
    )
    return f"{prefix}{count + 1:06d}"


@router.get("", response_model=list[SampleRead])
def list_samples(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)
) -> list[Sample]:
    del current_user
    return db.query(Sample).order_by(Sample.id.desc()).all()


@router.get("/quality-summary")
def sample_quality_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    """Indicateur qualité pré-analytique : répartition par aspect + taux de non-conformité.

    Le taux d'hémolyse / de non-conformité est un indicateur reconnu de la qualité
    du prélèvement (formation des préleveurs).
    """
    del current_user
    rows = db.query(Sample.aspect, func.count(Sample.id)).group_by(Sample.aspect).all()
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
    del current_user
    sample = db.query(Sample).filter(Sample.barcode == barcode).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun échantillon pour le code-barres {barcode}.",
        )
    return sample


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
    if not sample.lab_number:
        sample.lab_number = _next_lab_number(db)
    db.add(sample)
    db.flush()
    if sample.patient_id is not None:
        open_orders = (
            db.query(ExamOrder)
            .filter(
                ExamOrder.patient_id == sample.patient_id,
                ExamOrder.sample_id.is_(None),
                ExamOrder.status.in_(("prescribed", "collected", "in_progress")),
            )
            .order_by(ExamOrder.ordered_at.desc(), ExamOrder.id.desc())
            .limit(2)
            .all()
        )
        # Un seul bon ouvert : rattachement déterministe. S'il y en a plusieurs,
        # aucune supposition silencieuse n'est faite.
        if len(open_orders) == 1:
            open_orders[0].sample_id = sample.id
            open_orders[0].status = "collected"
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
    del current_user
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Echantillon introuvable.",
        )
    if payload.status is not None:
        sample.status = payload.status
    if payload.aspect is not None:
        sample.aspect = payload.aspect
    db.commit()
    db.refresh(sample)
    return sample

"""API — Tarifs d'examens (FCFA).

Lecture ouverte au personnel authentifié (pour pré-remplir une facture) ;
création/mise à jour réservées à la comptabilité (``require_finance``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_finance
from app.db.session import get_db
from app.models import ExamTariff, User
from app.schemas.tariff import ExamTariffRead, ExamTariffUpsert
from app.services.tariff_service import seed_tariffs

router = APIRouter(prefix="/tariffs")


@router.get("", response_model=list[ExamTariffRead])
def list_tariffs(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ExamTariff]:
    del current_user
    query = db.query(ExamTariff)
    if active_only:
        query = query.filter(ExamTariff.is_active.is_(True))
    return query.order_by(ExamTariff.exam_code).all()


@router.post("/seed-defaults")
def seed_default_tariffs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> dict[str, int]:
    """Crée les tarifs manquants depuis le catalogue d'examens (défauts à ajuster)."""
    del current_user
    return {"created": seed_tariffs(db)}


@router.put("/{exam_code}", response_model=ExamTariffRead)
def upsert_tariff(
    exam_code: str,
    payload: ExamTariffUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> ExamTariff:
    """Crée ou met à jour le tarif d'un examen (FCFA)."""
    del current_user
    tariff = db.query(ExamTariff).filter(ExamTariff.exam_code == exam_code).first()
    if tariff is None:
        tariff = ExamTariff(exam_code=exam_code)
        db.add(tariff)
    tariff.label = payload.label
    tariff.price_xof = payload.price_xof
    tariff.is_active = payload.is_active
    db.commit()
    db.refresh(tariff)
    return tariff

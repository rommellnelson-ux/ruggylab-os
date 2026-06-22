"""Service — tarifs d'examens (FCFA) pour la facturation automatique.

Les prix dépendent du laboratoire : ce module fournit un seed de défauts par
catégorie (à ajuster) et la résolution prix par code d'examen.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ExamTariff
from app.services.exam_catalog import EXAM_CATALOG

# Tarifs par défaut par catégorie (FCFA) — placeholders à ajuster par le labo.
_DEFAULT_BY_CATEGORY: dict[str, Decimal] = {
    "Hématologie": Decimal("5000"),
    "Biochimie": Decimal("3000"),
    "Sérologie": Decimal("8000"),
    "Parasitologie": Decimal("2500"),
    "Immunologie": Decimal("10000"),
    "Microbiologie": Decimal("6000"),
    "Hémostase": Decimal("4000"),
}
_DEFAULT_PRICE = Decimal("3000")


def default_price_for(category: str | None) -> Decimal:
    return _DEFAULT_BY_CATEGORY.get(category or "", _DEFAULT_PRICE)


def seed_tariffs(db: Session) -> int:
    """Crée les tarifs manquants depuis le catalogue d'examens (idempotent).

    Retourne le nombre de tarifs créés.
    """
    existing = {t.exam_code for t in db.query(ExamTariff.exam_code).all()}
    created = 0
    for exam in EXAM_CATALOG:
        code = exam["code"]
        if code in existing:
            continue
        db.add(
            ExamTariff(
                exam_code=code,
                label=exam.get("label", code),
                price_xof=default_price_for(exam.get("category")),
                is_active=True,
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def get_price(db: Session, exam_code: str) -> Decimal | None:
    """Prix actif d'un examen, ou None si non tarifé."""
    row = (
        db.query(ExamTariff)
        .filter(ExamTariff.exam_code == exam_code, ExamTariff.is_active.is_(True))
        .first()
    )
    return Decimal(row.price_xof) if row else None

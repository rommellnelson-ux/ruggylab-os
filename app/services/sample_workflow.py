"""Invariants transactionnels du cycle de vie des échantillons."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Sample

CANCELLED_SAMPLE_STATUS = "Annule"


class CancelledSampleError(RuntimeError):
    """L'échantillon annulé ne peut plus produire de résultat ni être collecté."""


def lock_sample_by_id(db: Session, sample_id: int) -> Sample | None:
    """Charge et verrouille un échantillon par identifiant jusqu'à la transaction."""
    return db.query(Sample).filter(Sample.id == sample_id).with_for_update().first()


def lock_sample_by_barcode(db: Session, barcode: str) -> Sample | None:
    """Charge et verrouille un échantillon par code-barres jusqu'à la transaction."""
    return db.query(Sample).filter(Sample.barcode == barcode).with_for_update().first()


def ensure_sample_processable(sample: Sample) -> None:
    """Refuse tout nouvel effet clinique sur un échantillon annulé."""
    if sample.status == CANCELLED_SAMPLE_STATUS:
        raise CancelledSampleError(
            f"L'échantillon {sample.barcode} est annulé et ne peut plus être traité."
        )

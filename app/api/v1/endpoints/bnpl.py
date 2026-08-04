"""
API — Suivi des échéances BNPL (Buy Now Pay Later / micro-crédit santé CMU)
===========================================================================

Endpoints :
  POST /billing/bnpl/schedule          → Créer un plan de paiement fractionné
  GET  /billing/bnpl/schedule/{id}     → Détail d'un plan + paiements
  POST /billing/bnpl/schedule/{id}/pay → Enregistrer un paiement d'échéance
  GET  /billing/bnpl/summary/{id}      → Résumé financier d'un plan
  GET  /billing/bnpl/overdue           → Plans avec échéances en retard
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_finance
from app.db.session import get_db
from app.models.bnpl import BNPLSchedule
from app.models.ruggylab_os import User
from app.schemas.bnpl import (
    BNPLPaymentCreate,
    BNPLPaymentOut,
    BNPLScheduleCreate,
    BNPLScheduleOut,
    BNPLSummary,
)
from app.services.accounting_service import apply_bnpl_installment_to_invoice
from app.services.audit import log_audit_event
from app.services.bnpl_tracker import BNPLTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/bnpl", tags=["BNPL CMU"])

_tracker = BNPLTracker()


@router.post(
    "/schedule",
    response_model=BNPLScheduleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un plan de paiement fractionné BNPL",
    description="Enregistre un plan BNPL et génère automatiquement les N échéances PENDING.",
)
def create_schedule(
    payload: BNPLScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> BNPLScheduleOut:
    """Crée un plan BNPL avec ses échéances."""
    result = _tracker.create_schedule(db, payload, commit=False)
    log_audit_event(
        db,
        user=current_user,
        event_type="bnpl.schedule.create",
        entity_type="bnpl_schedule",
        entity_id=str(result.id),
        payload={
            "total_amount_xof": result.total_amount_xof,
            "installment_months": result.installment_months,
        },
    )
    db.commit()
    logger.info(
        "bnpl.schedule.created",
        extra={
            "schedule_id": result.id,
            "total_amount_xof": result.total_amount_xof,
            "installment_months": result.installment_months,
        },
    )
    return result


@router.get(
    "/schedule/{schedule_id}",
    response_model=BNPLScheduleOut,
    summary="Détail d'un plan BNPL",
    description="Retourne le plan de paiement et toutes ses échéances.",
)
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_finance),
) -> BNPLScheduleOut:
    """Récupère un plan BNPL par son identifiant."""
    schedule = db.get(BNPLSchedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan BNPL {schedule_id} introuvable.",
        )
    return BNPLScheduleOut.model_validate(schedule)


@router.post(
    "/schedule/{schedule_id}/pay",
    response_model=BNPLPaymentOut,
    summary="Enregistrer un paiement d'échéance",
    description="Marque une échéance comme PAID. Met le plan à COMPLETED si toutes les échéances sont réglées.",
)
def record_payment(
    schedule_id: int,
    payload: BNPLPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_finance),
) -> BNPLPaymentOut:
    """Enregistre le paiement d'une échéance BNPL."""
    result = _tracker.record_payment(
        db,
        schedule_id,
        payload.installment_number,
        payload.amount_xof,
        commit=False,
    )
    # Cohérence comptable : répercute l'échéance sur la facture liée (le cas échéant).
    invoice = apply_bnpl_installment_to_invoice(db, schedule_id, payload.amount_xof)
    log_audit_event(
        db,
        user=current_user,
        event_type="bnpl.payment.record",
        entity_type="bnpl_payment",
        entity_id=str(result.id),
        payload={
            "schedule_id": schedule_id,
            "installment_number": payload.installment_number,
            "amount_xof": payload.amount_xof,
            "invoice_id": invoice.id if invoice is not None else None,
        },
    )
    db.commit()
    logger.info(
        "bnpl.payment.recorded",
        extra={
            "schedule_id": schedule_id,
            "installment_number": payload.installment_number,
            "amount_xof": payload.amount_xof,
        },
    )
    return result


@router.get(
    "/summary/{schedule_id}",
    response_model=BNPLSummary,
    summary="Résumé financier d'un plan BNPL",
    description="Calcule les montants payés, restants et le nombre d'échéances en retard.",
)
def get_summary(
    schedule_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_finance),
) -> BNPLSummary:
    """Retourne le résumé financier d'un plan BNPL."""
    return _tracker.get_summary(db, schedule_id)


@router.get(
    "/overdue",
    response_model=list[BNPLSummary],
    summary="Plans BNPL avec échéances en retard",
    description="Retourne tous les plans ayant au moins une échéance dont la due_date est dépassée et le statut PENDING.",
)
def get_overdue(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_finance),
) -> list[BNPLSummary]:
    """Liste tous les plans BNPL en situation de retard."""
    return _tracker.get_overdue(db)

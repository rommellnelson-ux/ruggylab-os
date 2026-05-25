"""Service de suivi des échéances BNPL (Buy Now Pay Later / micro-crédit santé CMU)."""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.bnpl import BNPLPayment, BNPLSchedule
from app.schemas.bnpl import (
    BNPLPaymentOut,
    BNPLScheduleCreate,
    BNPLScheduleOut,
    BNPLSummary,
)
from app.utils.datetime_utils import utcnow_naive


class BNPLTracker:
    """Gestion des plans de paiement fractionné BNPL."""

    def create_schedule(self, db: Session, data: BNPLScheduleCreate) -> BNPLScheduleOut:
        """Crée le plan + génère les N échéances PENDING (due_date = today + n*30j)."""
        # Calcul du montant mensuel (arrondi au XOF entier)
        base_monthly = data.total_amount_xof // data.installment_months
        remainder = data.total_amount_xof - base_monthly * data.installment_months
        # Le premier versement absorbe le reste de l'arrondi
        first_monthly = base_monthly + remainder

        schedule = BNPLSchedule(
            patient_ref=data.patient_ref,
            prescriber_id=data.prescriber_id,
            total_amount_xof=data.total_amount_xof,
            installment_months=data.installment_months,
            monthly_amount_xof=base_monthly,
            created_at=utcnow_naive(),
            status="ACTIVE",
        )
        db.add(schedule)
        db.flush()  # pour obtenir schedule.id

        today = dt.date.today()
        for n in range(1, data.installment_months + 1):
            due_date = today + dt.timedelta(days=30 * n)
            amount = first_monthly if n == 1 else base_monthly
            payment = BNPLPayment(
                schedule_id=schedule.id,
                installment_number=n,
                due_date=due_date,
                paid_at=None,
                amount_xof=amount,
                status="PENDING",
            )
            db.add(payment)

        db.commit()
        db.refresh(schedule)
        return BNPLScheduleOut.model_validate(schedule)

    def record_payment(
        self,
        db: Session,
        schedule_id: int,
        installment_number: int,
        amount_xof: int,
    ) -> BNPLPaymentOut:
        """Marque une échéance comme PAID, met à jour le statut du plan si complet."""
        schedule = db.get(BNPLSchedule, schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan BNPL {schedule_id} introuvable.",
            )

        payment = (
            db.query(BNPLPayment)
            .filter(
                BNPLPayment.schedule_id == schedule_id,
                BNPLPayment.installment_number == installment_number,
            )
            .first()
        )
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Échéance {installment_number} introuvable pour le plan {schedule_id}.",
            )

        if payment.status == "PAID":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Échéance {installment_number} déjà payée.",
            )

        payment.status = "PAID"
        payment.paid_at = utcnow_naive()
        payment.amount_xof = amount_xof

        # Vérifier si tous les paiements sont PAID ou WAIVED
        all_payments = (
            db.query(BNPLPayment)
            .filter(BNPLPayment.schedule_id == schedule_id)
            .all()
        )
        # Mettre à jour status en mémoire pour inclure le paiement courant
        pending_or_late = [
            p for p in all_payments
            if p.id != payment.id and p.status in ("PENDING", "LATE")
        ]
        if not pending_or_late:
            schedule.status = "COMPLETED"

        db.commit()
        db.refresh(payment)
        return BNPLPaymentOut.model_validate(payment)

    def get_summary(self, db: Session, schedule_id: int) -> BNPLSummary:
        """Calcule paid/remaining/overdue pour un plan."""
        schedule = db.get(BNPLSchedule, schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan BNPL {schedule_id} introuvable.",
            )

        payments = (
            db.query(BNPLPayment)
            .filter(BNPLPayment.schedule_id == schedule_id)
            .all()
        )

        today = dt.date.today()
        paid_amount = sum(p.amount_xof for p in payments if p.status in ("PAID", "WAIVED"))
        overdue_count = sum(
            1 for p in payments if p.status == "PENDING" and p.due_date < today
        )

        return BNPLSummary(
            schedule_id=schedule.id,
            patient_ref=schedule.patient_ref,
            total_amount_xof=schedule.total_amount_xof,
            paid_amount_xof=paid_amount,
            remaining_xof=schedule.total_amount_xof - paid_amount,
            overdue_count=overdue_count,
            status=schedule.status,
        )

    def get_overdue(self, db: Session) -> list[BNPLSummary]:
        """Retourne tous les plans avec au moins une échéance en retard (due_date < today et PENDING)."""
        today = dt.date.today()

        # Récupérer les schedule_id ayant des paiements en retard
        overdue_schedule_ids = (
            db.query(BNPLPayment.schedule_id)
            .filter(
                BNPLPayment.status == "PENDING",
                BNPLPayment.due_date < today,
            )
            .distinct()
            .all()
        )
        ids = [row[0] for row in overdue_schedule_ids]

        return [self.get_summary(db, sid) for sid in ids]

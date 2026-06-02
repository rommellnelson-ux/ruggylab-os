"""Modèles SQLAlchemy pour le suivi des échéances BNPL (Buy Now Pay Later / micro-crédit santé CMU)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.utils.datetime_utils import utcnow_naive


class BNPLSchedule(Base):
    """Plan de paiement fractionné enregistré en base."""

    __tablename__ = "bnpl_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_ref: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    prescriber_id: Mapped[str | None] = mapped_column(String(200))
    total_amount_xof: Mapped[int] = mapped_column(Integer, nullable=False)
    installment_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_amount_xof: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    payments: Mapped[list[BNPLPayment]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="BNPLPayment.installment_number",
    )


class BNPLPayment(Base):
    """Enregistrement d'un paiement d'échéance."""

    __tablename__ = "bnpl_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("bnpl_schedules.id"), nullable=False, index=True
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    amount_xof: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")

    schedule: Mapped[BNPLSchedule] = relationship(back_populates="payments")

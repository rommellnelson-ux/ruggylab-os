"""Lot de réactif — traçabilité fine par lot (méthode FEFO).

Plusieurs lots actifs par réactif ; on consomme en priorité le lot dont la
péremption est la plus proche (First-Expired-First-Out).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.utils.datetime_utils import utcnow_naive


class ReagentLot(Base):
    __tablename__ = "reagent_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reagent_id: Mapped[int] = mapped_column(ForeignKey("reagents.id"), nullable=False, index=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    # active | exhausted | expired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)

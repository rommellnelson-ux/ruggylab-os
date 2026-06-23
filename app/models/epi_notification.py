"""Notification épidémiologique (maladie à déclaration obligatoire — MADO).

Trace les pathologies à notifier au district sanitaire, avec le quartier de
résidence (cartographie de terrain) et le statut de transmission.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.utils.datetime_utils import utcnow_naive


class EpiNotification(Base):
    __tablename__ = "epi_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    patient_label: Mapped[str | None] = mapped_column(String(150))
    residence_quarter: Mapped[str | None] = mapped_column(String(150))
    pathology: Mapped[str] = mapped_column(String(150), nullable=False)
    sample_barcode: Mapped[str | None] = mapped_column(String(100))
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    # to_send | sent_to_district
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="to_send", index=True)
    notified_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    channel: Mapped[str | None] = mapped_column(String(100))
    declared_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

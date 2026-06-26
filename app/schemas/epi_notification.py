"""Schémas — Notification épidémiologique (MADO)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

EPI_STATUSES = ("to_send", "sent_to_district")


class EpiNotificationCreate(BaseModel):
    patient_id: int | None = None
    patient_label: str | None = Field(default=None, max_length=150)
    residence_quarter: str | None = Field(default=None, max_length=150)
    pathology: str = Field(..., min_length=1, max_length=150)
    sample_barcode: str | None = Field(default=None, max_length=100)
    model_config = ConfigDict(extra="forbid")


class EpiNotificationTransmit(BaseModel):
    channel: str | None = Field(default=None, max_length=100)
    model_config = ConfigDict(extra="forbid")


class EpiNotificationRead(BaseModel):
    id: int
    patient_id: int | None = None
    patient_label: str | None = None
    residence_quarter: str | None = None
    pathology: str
    sample_barcode: str | None = None
    detected_at: dt.datetime
    status: str
    notified_at: dt.datetime | None = None
    channel: str | None = None
    declared_by_id: int | None = None
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)

"""Schémas — Registre des Accidents d'Exposition au Sang (AES)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

EXPOSURE_TYPES = (
    "piqure",
    "coupure",
    "projection_muqueuse",
    "projection_peau_lesee",
    "autre",
)
AES_STATUSES = ("declared", "in_followup", "closed")


class AesCreate(BaseModel):
    agent_user_id: int | None = None
    agent_label: str | None = Field(default=None, max_length=150)
    occurred_at: dt.datetime
    location: str | None = Field(default=None, max_length=150)
    exposure_type: str = Field(default="piqure")
    circumstances: str = Field(..., min_length=1)
    immediate_measures: str | None = None
    source_label: str | None = Field(default=None, max_length=150)
    source_serology: str | None = Field(default=None, max_length=120)
    model_config = ConfigDict(extra="forbid")


class AesUpdate(BaseModel):
    status: str | None = None
    immediate_measures: str | None = None
    source_serology: str | None = Field(default=None, max_length=120)
    followup_notes: str | None = None
    model_config = ConfigDict(extra="forbid")


class AesRead(BaseModel):
    id: int
    agent_user_id: int | None = None
    agent_label: str | None = None
    declared_by_id: int | None = None
    occurred_at: dt.datetime
    location: str | None = None
    exposure_type: str
    circumstances: str
    immediate_measures: str | None = None
    source_label: str | None = None
    source_serology: str | None = None
    status: str
    followup_notes: str | None = None
    created_at: dt.datetime
    closed_at: dt.datetime | None = None
    model_config = ConfigDict(from_attributes=True)

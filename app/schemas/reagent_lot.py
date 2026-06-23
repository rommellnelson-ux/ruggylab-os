"""Schémas — Lots de réactifs (traçabilité FEFO)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ReagentLotCreate(BaseModel):
    reagent_id: int = Field(..., ge=1)
    lot_number: str = Field(..., min_length=1, max_length=100)
    expiry_date: dt.date | None = None
    quantity: float = Field(default=0.0, ge=0)
    model_config = ConfigDict(extra="forbid")


class ReagentLotConsume(BaseModel):
    reagent_id: int = Field(..., ge=1)
    quantity: float = Field(..., gt=0)
    model_config = ConfigDict(extra="forbid")


class ReagentLotRead(BaseModel):
    id: int
    reagent_id: int
    lot_number: str
    expiry_date: dt.date | None = None
    quantity: float
    received_at: dt.datetime
    status: str
    model_config = ConfigDict(from_attributes=True)

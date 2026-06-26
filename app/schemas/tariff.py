"""Schémas — Tarifs d'examens (FCFA) pour la facturation automatique."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExamTariffRead(BaseModel):
    id: int
    exam_code: str
    label: str
    price_xof: Decimal
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class ExamTariffUpsert(BaseModel):
    exam_code: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=150)
    price_xof: Decimal = Field(..., ge=0)
    is_active: bool = True
    model_config = ConfigDict(extra="forbid")

"""Schemas — Règles de delta-check patient."""
from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeltaCheckRuleCreate(BaseModel):
    analyte: str = Field(..., min_length=1, max_length=50)
    delta_pct: float | None = Field(None, gt=0, le=100, description="Seuil en % de variation")
    delta_abs: float | None = Field(None, gt=0, description="Seuil absolu de variation")
    lookback_days: int = Field(default=30, ge=1, le=365)
    unit: str = Field(default="", max_length=30)

    @model_validator(mode="after")
    def at_least_one_threshold(self) -> Self:
        if self.delta_pct is None and self.delta_abs is None:
            raise ValueError(
                "Au moins un seuil (delta_pct ou delta_abs) doit être défini."
            )
        return self


class DeltaCheckRuleRead(DeltaCheckRuleCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

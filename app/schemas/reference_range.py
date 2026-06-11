"""Schemas — Valeurs de référence par analyte/sexe/âge."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReferenceRangeCreate(BaseModel):
    analyte: str = Field(..., min_length=1, max_length=50)
    sex: Literal["M", "F", "*"] = Field(default="*", description="M / F / * (tous)")
    age_min_years: float | None = Field(None, ge=0, description="Âge minimum (années)")
    age_max_years: float | None = Field(None, ge=0, description="Âge maximum (années)")
    low_normal: float | None = None
    high_normal: float | None = None
    unit: str = Field(default="", max_length=30)

    @model_validator(mode="after")
    def at_least_one_bound(self) -> Self:
        if self.low_normal is None and self.high_normal is None:
            raise ValueError("Au moins une borne (low_normal ou high_normal) doit être définie.")
        return self


class ReferenceRangeRead(ReferenceRangeCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

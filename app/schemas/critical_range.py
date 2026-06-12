from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CriticalRangeCreate(BaseModel):
    analyte: str = Field(..., min_length=1, max_length=50)
    low_critical: float | None = None
    high_critical: float | None = None
    unit: str = Field(default="", max_length=30)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def at_least_one_bound(self) -> Self:
        if self.low_critical is None and self.high_critical is None:
            raise ValueError("Au moins un seuil (bas ou haut) doit être défini.")
        return self


class CriticalRangeRead(CriticalRangeCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

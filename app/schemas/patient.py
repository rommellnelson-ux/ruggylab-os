import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PatientBase(BaseModel):
    ipp_unique_id: str = Field(..., min_length=1, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: dt.date
    sex: str | None = Field(default=None, max_length=1)
    rank: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=100)

    @field_validator("sex")
    @classmethod
    def normalize_sex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in {"F", "M"}:
            raise ValueError("sex must be F or M")
        return normalized

    @model_validator(mode="after")
    def reject_future_birth_date(self) -> Self:
        if self.birth_date > dt.date.today():
            raise ValueError("birth_date cannot be in the future")
        return self


class PatientCreate(PatientBase):
    model_config = ConfigDict(extra="forbid")


class PatientUpdate(BaseModel):
    """Mise à jour partielle d'un patient (champs optionnels)."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    birth_date: dt.date | None = None
    sex: str | None = Field(default=None, max_length=1)
    rank: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("sex")
    @classmethod
    def normalize_sex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in {"F", "M"}:
            raise ValueError("sex must be F or M")
        return normalized

    @model_validator(mode="after")
    def reject_future_birth_date(self) -> Self:
        if self.birth_date is not None and self.birth_date > dt.date.today():
            raise ValueError("birth_date cannot be in the future")
        return self


class PatientRead(PatientBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

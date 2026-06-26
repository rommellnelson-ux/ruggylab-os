import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class TatTargetCreate(BaseModel):
    exam_code: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=100)
    target_minutes: int = Field(..., ge=1, le=100_000)
    warn_factor: float = Field(default=1.5, ge=1.0, le=10.0)
    model_config = ConfigDict(extra="forbid")


class TatTargetRead(BaseModel):
    id: int
    exam_code: str
    label: str
    target_minutes: int
    warn_factor: float
    is_active: bool = True
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class ResultTatUpdate(BaseModel):
    """Mise à jour des horodatages TAT d'un résultat (tous optionnels)."""

    exam_code: str | None = Field(default=None, max_length=50)
    prescribed_at: dt.datetime | None = None
    registered_at: dt.datetime | None = None
    collected_at: dt.datetime | None = None
    received_at: dt.datetime | None = None
    analysis_started_at: dt.datetime | None = None
    analysis_finished_at: dt.datetime | None = None
    tech_validated_at: dt.datetime | None = None
    bio_validated_at: dt.datetime | None = None
    released_at: dt.datetime | None = None
    model_config = ConfigDict(extra="forbid")

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class AutoValidationConfigCreate(BaseModel):
    name: str = Field(default="Règle par défaut", max_length=100)
    require_all_flags_normal: bool = True
    require_no_delta: bool = True
    require_not_critical: bool = True

    model_config = ConfigDict(extra="forbid")


class AutoValidationConfigRead(AutoValidationConfigCreate):
    id: int
    is_active: bool = True
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class AutoValidationRunResult(BaseModel):
    processed: int
    auto_validated: int
    error: str | None = None

import datetime as dt
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── QC dashboard summary ─────────────────────────────────────────────────────

QC_REJECT_RULES = frozenset({"1-3s", "2-2s", "R-4s", "4-1s", "10x"})


class QcStatusEntry(BaseModel):
    control_id: int
    analyte: str
    level: str
    unit: str
    last_date: dt.date | None
    last_value: float | None
    violations: list[str]
    status: str  # "ok" | "warn" | "reject" | "no_data"


class QcSummaryResponse(BaseModel):
    controls: list[QcStatusEntry]
    reject_count: int
    warn_count: int


class QcControlCreate(BaseModel):
    analyte: str = Field(..., min_length=1, max_length=100)
    level: str = Field(default="Niveau 1", max_length=50)
    unit: str = Field(default="", max_length=30)
    target_mean: float
    target_sd: float = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")


class QcControlRead(QcControlCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class QcResultCreate(BaseModel):
    control_id: int = Field(..., ge=1)
    value: float
    measured_at: dt.date
    operator: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(extra="forbid")


class QcResultRead(BaseModel):
    id: int
    control_id: int
    value: float
    measured_at: dt.date
    operator: str | None
    violations: list[str]
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("violations", mode="before")
    @classmethod
    def parse_violations(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        if isinstance(v, list):
            return v
        return []

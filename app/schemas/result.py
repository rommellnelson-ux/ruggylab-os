import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ResultBase(BaseModel):
    sample_id: int
    equipment_id: int | None = None
    analysis_date: dt.datetime | None = None
    data_points: dict = Field(default_factory=dict)
    image_url: str | None = None
    is_critical: bool = False


class ResultCreate(BaseModel):
    sample_id: int
    equipment_id: int | None = None
    analysis_date: dt.datetime | None = None
    data_points: dict = Field(default_factory=dict)
    image_url: str | None = None
    is_critical: bool = False

    model_config = ConfigDict(extra="forbid")


class ResultRead(ResultBase):
    id: int
    validator_id: int | None = None
    is_validated: bool = False
    critical_ack_at: dt.datetime | None = None
    critical_ack_by_id: int | None = None
    delta_exceeded: bool = False
    delta_analytes: dict | None = None
    flags: dict | None = None

    model_config = ConfigDict(from_attributes=True)

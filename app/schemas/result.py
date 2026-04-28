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


class ResultRead(ResultBase):
    id: int
    validator_id: int | None = None
    is_validated: bool = False

    model_config = ConfigDict(from_attributes=True)

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class PatientBase(BaseModel):
    ipp_unique_id: str = Field(..., min_length=1, max_length=50)
    first_name: str
    last_name: str
    birth_date: dt.date
    sex: str | None = Field(default=None, max_length=1)
    rank: str | None = None


class PatientCreate(PatientBase):
    pass


class PatientRead(PatientBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

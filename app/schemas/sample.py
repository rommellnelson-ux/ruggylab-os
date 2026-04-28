import datetime as dt

from pydantic import BaseModel, ConfigDict


class SampleBase(BaseModel):
    barcode: str
    patient_id: int | None = None
    collection_date: dt.datetime | None = None
    received_date: dt.datetime | None = None
    status: str | None = None


class SampleCreate(SampleBase):
    pass


class SampleRead(SampleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

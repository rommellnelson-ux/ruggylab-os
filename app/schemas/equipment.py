import datetime as dt

from pydantic import BaseModel, ConfigDict


class EquipmentBase(BaseModel):
    name: str
    serial_number: str | None = None
    type: str | None = None
    location: str | None = None
    last_calibration: dt.date | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentRead(EquipmentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

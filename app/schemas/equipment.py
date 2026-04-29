import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EquipmentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    last_calibration: dt.date | None = None

    @model_validator(mode="after")
    def reject_future_calibration(self) -> Self:
        if self.last_calibration and self.last_calibration > dt.date.today():
            raise ValueError("last_calibration cannot be in the future")
        return self


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentRead(EquipmentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

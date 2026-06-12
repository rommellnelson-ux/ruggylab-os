import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentMaintenanceCreate(BaseModel):
    equipment_id: int = Field(..., ge=1)
    maintenance_type: Literal["preventive", "corrective", "calibration"] = "preventive"
    scheduled_at: dt.datetime | None = None
    next_due_at: dt.datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class EquipmentMaintenanceRead(BaseModel):
    id: int
    equipment_id: int
    maintenance_type: str
    scheduled_at: dt.datetime | None = None
    performed_at: dt.datetime | None = None
    performed_by_id: int | None = None
    notes: str | None = None
    next_due_at: dt.datetime | None = None
    is_completed: bool = False
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)

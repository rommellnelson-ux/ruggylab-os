import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ReagentBase(BaseModel):
    name: str
    category: str | None = None
    unit: str = "unit"
    current_stock: float = Field(default=0.0, ge=0)
    alert_threshold: float = Field(default=0.0, ge=0)
    lot_number: str | None = None
    expiry_date: dt.date | None = None
    supplier: str | None = None


class ReagentCreate(ReagentBase):
    model_config = ConfigDict(extra="forbid")


class ReagentRead(ReagentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

from pydantic import BaseModel, ConfigDict


class ReagentBase(BaseModel):
    name: str
    category: str | None = None
    unit: str = "unit"
    current_stock: float = 0.0
    alert_threshold: float = 0.0


class ReagentCreate(ReagentBase):
    pass


class ReagentRead(ReagentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

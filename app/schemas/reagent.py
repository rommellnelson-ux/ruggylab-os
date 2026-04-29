from pydantic import BaseModel, ConfigDict, Field


class ReagentBase(BaseModel):
    name: str
    category: str | None = None
    unit: str = "unit"
    current_stock: float = Field(default=0.0, ge=0)
    alert_threshold: float = Field(default=0.0, ge=0)


class ReagentCreate(ReagentBase):
    pass


class ReagentRead(ReagentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

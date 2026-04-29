from pydantic import BaseModel, ConfigDict, Field


class RatioPresetBase(BaseModel):
    name: str
    equipment_name: str
    description: str | None = None
    is_active: bool = True


class RatioPresetCreate(RatioPresetBase):
    pass


class RatioPresetRead(RatioPresetBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class RatioPresetItemBase(BaseModel):
    reagent_name: str
    reagent_category: str | None = None
    reagent_unit: str = "unit"
    consumption_per_run: float = Field(ge=0)
    adjustment_factor: float = Field(default=1.0, gt=0)
    notes: str | None = None
    is_active: bool = True


class RatioPresetItemCreate(RatioPresetItemBase):
    preset_id: int


class RatioPresetItemRead(RatioPresetItemBase):
    id: int
    preset_id: int

    model_config = ConfigDict(from_attributes=True)

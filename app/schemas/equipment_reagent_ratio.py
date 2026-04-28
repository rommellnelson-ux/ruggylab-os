from pydantic import BaseModel, ConfigDict


class EquipmentReagentRatioBase(BaseModel):
    equipment_id: int
    reagent_id: int
    consumption_per_run: float
    adjustment_factor: float = 1.0
    notes: str | None = None
    is_active: bool = True


class EquipmentReagentRatioCreate(EquipmentReagentRatioBase):
    pass


class EquipmentReagentRatioUpdate(BaseModel):
    consumption_per_run: float | None = None
    adjustment_factor: float | None = None
    notes: str | None = None
    is_active: bool | None = None


class EquipmentReagentRatioRead(EquipmentReagentRatioBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class EquipmentReagentRatioVersionRead(BaseModel):
    id: int
    ratio_id: int
    version_number: int
    equipment_id: int
    reagent_id: int
    consumption_per_run: float
    adjustment_factor: float
    notes: str | None = None
    is_active: bool
    changed_by_user_id: int | None = None
    change_reason: str | None = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)

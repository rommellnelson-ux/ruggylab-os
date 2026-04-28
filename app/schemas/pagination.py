from pydantic import BaseModel, ConfigDict

from app.schemas.audit_event import AuditEventRead
from app.schemas.equipment_reagent_ratio import EquipmentReagentRatioRead
from app.schemas.patient import PatientRead
from app.schemas.reagent import ReagentRead
from app.schemas.ratio_preset import RatioPresetItemRead, RatioPresetRead
from app.schemas.result import ResultRead


class PaginationMeta(BaseModel):
    total: int
    skip: int
    limit: int


class PatientListResponse(BaseModel):
    items: list[PatientRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class ResultListResponse(BaseModel):
    items: list[ResultRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class ReagentListResponse(BaseModel):
    items: list[ReagentRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class EquipmentReagentRatioListResponse(BaseModel):
    items: list[EquipmentReagentRatioRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class RatioPresetListResponse(BaseModel):
    items: list[RatioPresetRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)


class RatioPresetItemListResponse(BaseModel):
    items: list[RatioPresetItemRead]
    meta: PaginationMeta

    model_config = ConfigDict(from_attributes=True)

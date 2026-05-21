from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.schemas.audit_event import AuditEventRead
from app.schemas.equipment_reagent_ratio import EquipmentReagentRatioRead
from app.schemas.patient import PatientRead
from app.schemas.ratio_preset import RatioPresetItemRead, RatioPresetRead
from app.schemas.reagent import ReagentRead
from app.schemas.result import ResultRead


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    skip: int = Field(
        default=0,
        ge=0,
        description="Number of items to skip (offset)",
    )
    limit: int = Field(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Number of items to return (per page)",
    )

    def validate_and_adjust(self) -> "PaginationParams":
        """Validate and adjust pagination parameters."""
        if self.limit > settings.MAX_PAGE_SIZE:
            self.limit = settings.MAX_PAGE_SIZE
        return self


class PaginationMeta(BaseModel):
    total: int
    skip: int
    limit: int
    pages: int = Field(description="Total number of pages")

    @classmethod
    def from_counts(cls, total: int, skip: int, limit: int) -> "PaginationMeta":
        """Create pagination metadata from counts."""
        pages = (total + limit - 1) // limit if limit > 0 else 1
        return cls(total=total, skip=skip, limit=limit, pages=pages)


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

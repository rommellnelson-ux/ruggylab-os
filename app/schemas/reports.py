from pydantic import BaseModel, ConfigDict

from app.schemas.audit_event import AuditEventRead
from app.schemas.reagent import ReagentRead


class MonthlyConsumptionEntry(BaseModel):
    reagent_name: str
    category: str | None = None
    current_stock: float
    alert_threshold: float
    estimated_monthly_consumption: float
    actual_run_count: int = 0
    source_equipment: list[str] = []
    days_of_cover: float | None = None


class CriticalThresholdEntry(BaseModel):
    reagent_name: str
    current_stock: float
    alert_threshold: float
    gap_to_threshold: float
    severity: str


class AuditActivityEntry(BaseModel):
    username: str
    event_date: str
    event_count: int


class StockDashboardResponse(BaseModel):
    total_reagents: int
    low_stock_reagents: list[ReagentRead]
    total_stock_units: float

    model_config = ConfigDict(from_attributes=True)


class AuditDashboardResponse(BaseModel):
    total_events: int
    recent_events: list[AuditEventRead]
    event_type_breakdown: dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class MonthlyConsumptionDashboardResponse(BaseModel):
    month: str
    items: list[MonthlyConsumptionEntry]


class CriticalThresholdDashboardResponse(BaseModel):
    total_critical_reagents: int
    items: list[CriticalThresholdEntry]


class AuditUserActivityDashboardResponse(BaseModel):
    items: list[AuditActivityEntry]

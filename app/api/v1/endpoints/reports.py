from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_admin
from app.db.session import get_db
from app.models import AuditEvent, EquipmentReagentRatio, Reagent, Result, User
from app.schemas.audit_event import AuditEventRead
from app.schemas.reagent import ReagentRead
from app.schemas.reports import (
    AuditActivityEntry,
    AuditDashboardResponse,
    AuditUserActivityDashboardResponse,
    CriticalThresholdDashboardResponse,
    CriticalThresholdEntry,
    MonthlyConsumptionDashboardResponse,
    MonthlyConsumptionEntry,
    StockDashboardResponse,
)

router = APIRouter(prefix="/reports")


@router.get("/stock-dashboard", response_model=StockDashboardResponse)
def stock_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StockDashboardResponse:
    del current_user
    low_stock = (
        db.query(Reagent)
        .filter(Reagent.current_stock <= Reagent.alert_threshold)
        .order_by(Reagent.current_stock.asc())
        .all()
    )
    total_reagents = db.query(func.count(Reagent.id)).scalar() or 0
    total_stock_units = (
        db.query(func.coalesce(func.sum(Reagent.current_stock), 0.0)).scalar() or 0.0
    )
    return StockDashboardResponse(
        total_reagents=total_reagents,
        low_stock_reagents=[ReagentRead.model_validate(item) for item in low_stock],
        total_stock_units=float(total_stock_units),
    )


@router.get(
    "/audit-dashboard",
    response_model=AuditDashboardResponse,
    dependencies=[Depends(require_admin)],
)
def audit_dashboard(db: Session = Depends(get_db)) -> AuditDashboardResponse:
    total_events = db.query(func.count(AuditEvent.id)).scalar() or 0
    recent = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(20).all()
    grouped = (
        db.query(AuditEvent.event_type, func.count(AuditEvent.id))
        .group_by(AuditEvent.event_type)
        .all()
    )
    breakdown = {event_type: count for event_type, count in grouped}
    return AuditDashboardResponse(
        total_events=total_events,
        recent_events=[AuditEventRead.model_validate(item) for item in recent],
        event_type_breakdown=breakdown,
    )


@router.get("/monthly-consumption", response_model=MonthlyConsumptionDashboardResponse)
def monthly_consumption_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    year: int = Query(default_factory=lambda: datetime.now(UTC).year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: datetime.now(UTC).month, ge=1, le=12),
) -> MonthlyConsumptionDashboardResponse:
    del current_user
    monthly_result_counts = dict(
        db.query(Result.equipment_id, func.count(Result.id))
        .filter(func.extract("year", Result.analysis_date) == year)
        .filter(func.extract("month", Result.analysis_date) == month)
        .filter(Result.equipment_id.is_not(None))
        .group_by(Result.equipment_id)
        .all()
    )

    reagent_usage_map: dict[str, dict[str, object]] = {}
    ratios = (
        db.query(EquipmentReagentRatio)
        .filter(EquipmentReagentRatio.is_active.is_(True))
        .all()
    )
    for ratio in ratios:
        run_count = int(monthly_result_counts.get(ratio.equipment_id, 0))
        if run_count <= 0:
            continue
        usage = reagent_usage_map.setdefault(
            ratio.reagent.name,
            {
                "estimated_monthly_consumption": 0.0,
                "actual_run_count": 0,
                "source_equipment": set(),
            },
        )
        adjusted_ratio = ratio.consumption_per_run * ratio.adjustment_factor
        usage["estimated_monthly_consumption"] = float(
            usage["estimated_monthly_consumption"]
        ) + (run_count * adjusted_ratio)
        usage["actual_run_count"] = int(usage["actual_run_count"]) + run_count
        usage["source_equipment"].add(ratio.equipment.name)

    items: list[MonthlyConsumptionEntry] = []
    reagents = db.query(Reagent).order_by(Reagent.name.asc()).all()
    for reagent in reagents:
        usage = reagent_usage_map.get(
            reagent.name,
            {
                "estimated_monthly_consumption": 0.0,
                "actual_run_count": 0,
                "source_equipment": set(),
            },
        )
        estimated_monthly_consumption = float(usage["estimated_monthly_consumption"])
        days_of_cover = None
        if estimated_monthly_consumption > 0:
            daily_rate = estimated_monthly_consumption / 30.0
            days_of_cover = round(reagent.current_stock / daily_rate, 2)
        items.append(
            MonthlyConsumptionEntry(
                reagent_name=reagent.name,
                category=reagent.category,
                current_stock=reagent.current_stock,
                alert_threshold=reagent.alert_threshold,
                estimated_monthly_consumption=estimated_monthly_consumption,
                actual_run_count=int(usage["actual_run_count"]),
                source_equipment=sorted(list(usage["source_equipment"])),
                days_of_cover=days_of_cover,
            )
        )
    return MonthlyConsumptionDashboardResponse(
        month=f"{year:04d}-{month:02d}", items=items
    )


@router.get("/critical-thresholds", response_model=CriticalThresholdDashboardResponse)
def critical_threshold_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CriticalThresholdDashboardResponse:
    del current_user
    reagents = (
        db.query(Reagent)
        .filter(Reagent.current_stock <= Reagent.alert_threshold)
        .order_by(Reagent.current_stock.asc())
        .all()
    )
    items: list[CriticalThresholdEntry] = []
    for reagent in reagents:
        gap = round(reagent.current_stock - reagent.alert_threshold, 2)
        severity = "critical" if reagent.current_stock <= 0 else "warning"
        items.append(
            CriticalThresholdEntry(
                reagent_name=reagent.name,
                current_stock=reagent.current_stock,
                alert_threshold=reagent.alert_threshold,
                gap_to_threshold=gap,
                severity=severity,
            )
        )
    return CriticalThresholdDashboardResponse(
        total_critical_reagents=len(items), items=items
    )


@router.get(
    "/audit-activity",
    response_model=AuditUserActivityDashboardResponse,
    dependencies=[Depends(require_admin)],
)
def audit_activity_dashboard(
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90),
) -> AuditUserActivityDashboardResponse:
    start_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days - 1)
    event_day = func.date(AuditEvent.created_at)
    grouped = (
        db.query(
            User.username,
            event_day.label("event_date"),
            func.count(AuditEvent.id).label("event_count"),
        )
        .join(User, User.id == AuditEvent.user_id, isouter=True)
        .filter(AuditEvent.created_at >= start_date)
        .group_by(User.username, event_day)
        .order_by(event_day.desc(), User.username.asc())
        .all()
    )
    items: list[AuditActivityEntry] = []
    for username, event_date, event_count in grouped:
        if not event_date:
            continue
        items.append(
            AuditActivityEntry(
                username=username or "unknown",
                event_date=str(event_date),
                event_count=int(event_count),
            )
        )
    return AuditUserActivityDashboardResponse(items=items)

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_admin, require_officer
from app.db.session import get_db
from app.models import (
    AuditEvent,
    EquipmentReagentRatio,
    Patient,
    Reagent,
    ReportSignature,
    Result,
    Sample,
    User,
)
from app.schemas.audit_event import AuditEventRead
from app.schemas.reagent import ReagentRead
from app.schemas.report_signature import ReportSignatureCreate, ReportSignatureRead
from app.schemas.reports import (
    AuditActivityEntry,
    AuditDashboardResponse,
    AuditUserActivityDashboardResponse,
    CriticalThresholdDashboardResponse,
    CriticalThresholdEntry,
    EpidemiologyMarkerEntry,
    EpidemiologySummaryResponse,
    MonthlyConsumptionDashboardResponse,
    MonthlyConsumptionEntry,
    StockDashboardResponse,
)
from app.services.report_signing import build_result_report_pdf, create_report_signature

router = APIRouter(prefix="/reports")

EPIDEMIOLOGY_MARKERS = ("WBC", "RBC", "HGB", "HCT", "MCV", "MCH", "MCHC", "PLT")


def _get_result_or_404(db: Session, result_id: int) -> Result:
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resultat introuvable.",
        )
    return result


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


def _epidemiology_results(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
) -> list[Result]:
    return (
        db.query(Result)
        .filter(Result.analysis_date >= start_date)
        .filter(Result.analysis_date <= end_date)
        .order_by(Result.analysis_date.desc())
        .all()
    )


def _marker_status(value: object) -> tuple[str | None, bool]:
    if not isinstance(value, dict):
        return None, False
    status_value = value.get("status")
    status = str(status_value).upper() if status_value else None
    return status, bool(value.get("is_critical", False))


def _build_epidemiology_summary(
    results: list[Result],
    *,
    start_date: datetime,
    end_date: datetime,
) -> EpidemiologySummaryResponse:
    sex_breakdown: dict[str, int] = {}
    marker_counts = {
        marker: {"total": 0, "low": 0, "normal": 0, "high": 0, "critical": 0}
        for marker in EPIDEMIOLOGY_MARKERS
    }
    malaria_positive = 0
    malaria_negative = 0

    for result in results:
        patient = result.sample.patient if result.sample else None
        sex = patient.sex if patient and patient.sex else "unknown"
        sex_breakdown[sex] = sex_breakdown.get(sex, 0) + 1

        data_points = result.data_points or {}
        malaria_ai = data_points.get("malaria_ai")
        if isinstance(malaria_ai, dict):
            label = str(malaria_ai.get("label", "")).lower()
            if label == "positive":
                malaria_positive += 1
            elif label == "negative":
                malaria_negative += 1

        for marker in EPIDEMIOLOGY_MARKERS:
            status_value, is_critical = _marker_status(data_points.get(marker))
            if status_value is None:
                continue
            counts = marker_counts[marker]
            counts["total"] += 1
            if status_value == "L":
                counts["low"] += 1
            elif status_value == "H":
                counts["high"] += 1
            elif status_value == "N":
                counts["normal"] += 1
            if is_critical:
                counts["critical"] += 1

    return EpidemiologySummaryResponse(
        period_start=start_date.date().isoformat(),
        period_end=end_date.date().isoformat(),
        total_results=len(results),
        critical_results=sum(1 for result in results if result.is_critical),
        malaria_positive=malaria_positive,
        malaria_negative=malaria_negative,
        sex_breakdown=sex_breakdown,
        marker_breakdown=[
            EpidemiologyMarkerEntry(marker=marker, **counts)
            for marker, counts in marker_counts.items()
            if counts["total"] > 0
        ],
    )


@router.get(
    "/epidemiology-summary",
    response_model=EpidemiologySummaryResponse,
)
def epidemiology_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(default=30, ge=1, le=366),
) -> EpidemiologySummaryResponse:
    del current_user
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    results = _epidemiology_results(db, start_date=start_date, end_date=end_date)
    return _build_epidemiology_summary(
        results, start_date=start_date, end_date=end_date
    )


@router.get("/epidemiology-export.csv")
def epidemiology_export_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(default=30, ge=1, le=366),
) -> Response:
    del current_user
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    results = (
        db.query(Result)
        .join(Sample, Sample.id == Result.sample_id)
        .join(Patient, Patient.id == Sample.patient_id, isouter=True)
        .filter(Result.analysis_date >= start_date)
        .filter(Result.analysis_date <= end_date)
        .order_by(Result.analysis_date.desc())
        .all()
    )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "result_id",
            "analysis_date",
            "sample_barcode",
            "patient_ipp",
            "patient_sex",
            "is_critical",
            "malaria_label",
            "malaria_confidence",
        ]
        + list(EPIDEMIOLOGY_MARKERS)
    )
    for result in results:
        patient = result.sample.patient if result.sample else None
        data_points = result.data_points or {}
        malaria_ai = data_points.get("malaria_ai")
        malaria_label = ""
        malaria_confidence = ""
        if isinstance(malaria_ai, dict):
            malaria_label = malaria_ai.get("label", "")
            malaria_confidence = malaria_ai.get("confidence", "")
        writer.writerow(
            [
                result.id,
                result.analysis_date.isoformat(),
                result.sample.barcode if result.sample else "",
                patient.ipp_unique_id if patient else "",
                patient.sex if patient and patient.sex else "",
                result.is_critical,
                malaria_label,
                malaria_confidence,
            ]
            + [
                (
                    data_points.get(marker, {}).get("value", "")
                    if isinstance(data_points.get(marker), dict)
                    else data_points.get(marker, "")
                )
                for marker in EPIDEMIOLOGY_MARKERS
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="epidemiology-export.csv"'
        },
    )


@router.get("/results/{result_id}/pdf")
def result_report_pdf(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    del current_user
    result = _get_result_or_404(db, result_id)
    signature = (
        db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    )
    pdf_bytes = build_result_report_pdf(result, signature)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="result-{result_id}.pdf"',
        },
    )


@router.post(
    "/results/{result_id}/sign",
    response_model=ReportSignatureRead,
    status_code=status.HTTP_201_CREATED,
)
def sign_result_report(
    result_id: int,
    payload: ReportSignatureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> ReportSignature:
    result = _get_result_or_404(db, result_id)
    if not result.is_validated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Signature impossible: le resultat n'est pas valide.",
        )

    existing = (
        db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rapport deja signe pour ce resultat.",
        )

    return create_report_signature(
        db,
        result=result,
        user=current_user,
        signature_meaning=payload.signature_meaning,
    )


@router.get(
    "/results/{result_id}/signature",
    response_model=ReportSignatureRead,
)
def get_result_report_signature(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportSignature:
    del current_user
    signature = (
        db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature de rapport introuvable.",
        )
    return signature


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

import csv
import datetime as dt
import json
from datetime import UTC, datetime, timedelta
from html import escape as html_escape
from io import StringIO
from typing import Literal, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import forbid_accountant, get_current_active_user, require_admin, require_officer
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditEvent,
    EquipmentReagentRatio,
    Patient,
    QcControl,
    QcResult,
    Reagent,
    ReportSignature,
    ReportSnapshot,
    Result,
    Sample,
    User,
)
from app.schemas.audit_event import AuditEventRead
from app.schemas.qc import QC_REJECT_RULES, QcStatusEntry, QcSummaryResponse
from app.schemas.reagent import ReagentRead
from app.schemas.report_signature import (
    ReportReleaseCreate,
    ReportSignatureCreate,
    ReportSignatureRead,
    ReportSnapshotRead,
    ReportSnapshotRevoke,
    ReportVerifyRead,
)
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
from app.services.audit import log_audit_event
from app.services.patient_access import apply_result_patient_scope, can_access_result
from app.services.qc_pdf_report import build_qc_html_report
from app.services.report_signing import (
    build_result_report_pdf,
    build_snapshot_pdf,
    create_report_signature,
    reissue_report_signature,
    release_result_report,
    report_snapshot_token_hash,
)
from app.utils.csv_safety import sanitize_csv_cell
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/reports")

EPIDEMIOLOGY_MARKERS = ("WBC", "RBC", "HGB", "HCT", "MCV", "MCH", "MCHC", "PLT")


class _ReagentUsageBucket(TypedDict):
    estimated_monthly_consumption: float
    actual_run_count: int
    source_equipment: set[str]


def _get_result_or_404(db: Session, result_id: int) -> Result:
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resultat introuvable.",
        )
    return result


def _get_accessible_result_or_error(db: Session, result_id: int, user: User) -> Result:
    result = _get_result_or_404(db, result_id)
    if not can_access_result(user, result):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au résultat hors de votre périmètre.",
        )
    return result


def _get_accessible_snapshot_or_error(db: Session, snapshot_id: int, user: User) -> ReportSnapshot:
    snapshot = db.query(ReportSnapshot).filter(ReportSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version de compte-rendu introuvable.",
        )
    if not can_access_result(user, snapshot.result):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au compte-rendu hors de votre périmètre.",
        )
    return snapshot


def _ensure_releasable_result(result: Result) -> None:
    # Validation non bloquante par défaut (effectif réduit, pas de double
    # validation quotidienne) : publiable « provisoire », validé a posteriori.
    # Réglage REQUIRE_VALIDATION_FOR_RELEASE pour revenir au mode ISO strict.
    if settings.REQUIRE_VALIDATION_FOR_RELEASE and not result.is_validated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Publication impossible: le resultat n'est pas valide.",
        )
    # Sécurité patient : une valeur critique non prise en charge reste bloquante.
    if result.is_critical and result.critical_ack_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Publication impossible: valeur critique non prise en charge.",
        )


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


@router.get("/qc-summary", response_model=QcSummaryResponse)
def qc_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> QcSummaryResponse:
    """Return the latest QC result status for every active control."""
    del current_user
    controls = (
        db.query(QcControl)
        .filter(QcControl.is_active.is_(True))
        .order_by(QcControl.analyte, QcControl.level)
        .all()
    )
    entries: list[QcStatusEntry] = []
    for ctrl in controls:
        last: QcResult | None = (
            db.query(QcResult)
            .filter(QcResult.control_id == ctrl.id)
            .order_by(QcResult.measured_at.desc(), QcResult.id.desc())
            .first()
        )
        if last:
            violations: list[str] = json.loads(last.violations or "[]")
            if any(r in QC_REJECT_RULES for r in violations):
                qc_status = "reject"
            elif violations:
                qc_status = "warn"
            else:
                qc_status = "ok"
            entry = QcStatusEntry(
                control_id=ctrl.id,
                analyte=ctrl.analyte,
                level=ctrl.level,
                unit=ctrl.unit,
                last_date=last.measured_at,
                last_value=last.value,
                violations=violations,
                status=qc_status,
            )
        else:
            entry = QcStatusEntry(
                control_id=ctrl.id,
                analyte=ctrl.analyte,
                level=ctrl.level,
                unit=ctrl.unit,
                last_date=None,
                last_value=None,
                violations=[],
                status="no_data",
            )
        entries.append(entry)

    return QcSummaryResponse(
        controls=entries,
        reject_count=sum(1 for e in entries if e.status == "reject"),
        warn_count=sum(1 for e in entries if e.status == "warn"),
    )


def _epidemiology_results(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    user: User,
) -> list[Result]:
    query = apply_result_patient_scope(db.query(Result), user)
    return cast(
        list[Result],
        (
            query.filter(Result.analysis_date >= start_date)
            .filter(Result.analysis_date <= end_date)
            .order_by(Result.analysis_date.desc())
            .all()
        ),
    )


def _marker_status(value: object) -> tuple[str | None, bool]:
    if not isinstance(value, dict):
        return None, False
    status_value = value.get("status")
    report_status = str(status_value).upper() if status_value else None
    return report_status, bool(value.get("is_critical", False))


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
    current_user: User = Depends(forbid_accountant),
    days: int = Query(default=30, ge=1, le=366),
) -> EpidemiologySummaryResponse:
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    results = _epidemiology_results(
        db,
        start_date=start_date,
        end_date=end_date,
        user=current_user,
    )
    return _build_epidemiology_summary(results, start_date=start_date, end_date=end_date)


@router.get("/epidemiology-export.csv")
def epidemiology_export_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
    days: int = Query(default=30, ge=1, le=366),
) -> Response:
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    results = _epidemiology_results(
        db,
        start_date=start_date,
        end_date=end_date,
        user=current_user,
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
                sanitize_csv_cell(x)
                for x in (
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
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="epidemiology-export.csv"'},
    )


@router.get("/results/{result_id}/pdf")
def result_report_pdf(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
) -> Response:
    result = _get_accessible_result_or_error(db, result_id, current_user)
    signature = db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
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
) -> ReportSignatureRead:
    result = _get_accessible_result_or_error(db, result_id, current_user)
    _ensure_releasable_result(result)

    existing = db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    if existing and existing.revoked_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rapport deja signe pour ce resultat.",
        )

    try:
        signature = (
            reissue_report_signature(
                db,
                signature=existing,
                result=result,
                user=current_user,
                signature_meaning=payload.signature_meaning,
                commit=False,
            )
            if existing
            else create_report_signature(
                db,
                result=result,
                user=current_user,
                signature_meaning=payload.signature_meaning,
                commit=False,
            )
        )
        release_result_report(
            db,
            result=result,
            user=current_user,
            signature=signature,
            commit=False,
        )
        db.flush()
        response = ReportSignatureRead.model_validate(signature)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


@router.get(
    "/results/{result_id}/signature",
    response_model=ReportSignatureRead,
)
def get_result_report_signature(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
) -> ReportSignature:
    _get_accessible_result_or_error(db, result_id, current_user)
    signature = db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature de rapport introuvable.",
        )
    return signature


@router.post(
    "/results/{result_id}/release",
    response_model=ReportSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def release_result_report_endpoint(
    result_id: int,
    payload: ReportReleaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> ReportSnapshot:
    result = _get_accessible_result_or_error(db, result_id, current_user)
    _ensure_releasable_result(result)
    signature = (
        db.query(ReportSignature)
        .filter(ReportSignature.result_id == result_id, ReportSignature.revoked_at.is_(None))
        .first()
    )
    return release_result_report(
        db,
        result=result,
        user=current_user,
        audience=payload.audience,
        signature=signature,
        delivery_channels=list(payload.delivery_channels),
    )


@router.get("/results/{result_id}/snapshots", response_model=list[ReportSnapshotRead])
def list_result_report_snapshots(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
) -> list[ReportSnapshot]:
    _get_accessible_result_or_error(db, result_id, current_user)
    return (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.result_id == result_id)
        .order_by(ReportSnapshot.version_number.desc(), ReportSnapshot.id.desc())
        .all()
    )


@router.get("/snapshots/{snapshot_id}/pdf")
def report_snapshot_pdf(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
) -> Response:
    snapshot = _get_accessible_snapshot_or_error(db, snapshot_id, current_user)
    return Response(
        content=build_snapshot_pdf(snapshot),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="result-{snapshot.result_id}-v{snapshot.version_number}.pdf"'
            ),
        },
    )


@router.post("/snapshots/{snapshot_id}/revoke", response_model=ReportSnapshotRead)
def revoke_report_snapshot(
    snapshot_id: int,
    payload: ReportSnapshotRevoke,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> ReportSnapshot:
    snapshot = _get_accessible_snapshot_or_error(db, snapshot_id, current_user)
    if snapshot.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Compte-rendu deja revoque.",
        )
    snapshot.status = "revoked"
    snapshot.revoked_at = utcnow_naive()
    snapshot.revocation_reason = payload.reason
    log_audit_event(
        db,
        user=current_user,
        event_type="report.revoke",
        entity_type="report_snapshot",
        entity_id=str(snapshot.id),
        payload={
            "result_id": snapshot.result_id,
            "version_number": snapshot.version_number,
            "reason": payload.reason,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/verify/{token}", response_model=ReportVerifyRead)
def verify_report_snapshot(
    token: str,
    db: Session = Depends(get_db),
) -> ReportVerifyRead:
    snapshot = (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.verification_token_hash == report_snapshot_token_hash(token))
        .first()
    )
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte-rendu introuvable ou jeton invalide.",
        )
    public_status: Literal["valid", "provisional", "corrected", "revoked"]
    if snapshot.revoked_at is not None or snapshot.status == "revoked":
        public_status = "revoked"
    elif snapshot.status == "corrected":
        public_status = "corrected"
    elif snapshot.status == "provisional":
        public_status = "provisional"
    else:
        public_status = "valid"
    return ReportVerifyRead(
        status=public_status,
        snapshot_id=snapshot.id,
        result_id=snapshot.result_id,
        version_number=snapshot.version_number,
        document_status=snapshot.status,
        created_at=snapshot.created_at,
        pdf_sha256=snapshot.pdf_sha256,
        revoked_at=snapshot.revoked_at,
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
    breakdown: dict[str, int] = {str(et): int(cnt) for et, cnt in grouped}
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
    equip_rows = (
        db.query(Result.equipment_id, func.count(Result.id))
        .filter(func.extract("year", Result.analysis_date) == year)
        .filter(func.extract("month", Result.analysis_date) == month)
        .filter(Result.equipment_id.is_not(None))
        .group_by(Result.equipment_id)
        .all()
    )
    monthly_result_counts: dict[int, int] = {
        int(eid): int(cnt) for eid, cnt in equip_rows if eid is not None
    }

    reagent_usage_map: dict[str, _ReagentUsageBucket] = {}
    ratios = db.query(EquipmentReagentRatio).filter(EquipmentReagentRatio.is_active.is_(True)).all()
    for ratio in ratios:
        run_count = int(monthly_result_counts.get(ratio.equipment_id, 0))
        if run_count <= 0:
            continue
        usage = reagent_usage_map.setdefault(
            ratio.reagent.name,
            _ReagentUsageBucket(
                estimated_monthly_consumption=0.0,
                actual_run_count=0,
                source_equipment=set(),
            ),
        )
        adjusted_ratio = ratio.consumption_per_run * ratio.adjustment_factor
        usage["estimated_monthly_consumption"] = float(usage["estimated_monthly_consumption"]) + (
            run_count * adjusted_ratio
        )
        usage["actual_run_count"] = int(usage["actual_run_count"]) + run_count
        usage["source_equipment"].add(ratio.equipment.name)

    items: list[MonthlyConsumptionEntry] = []
    reagents = db.query(Reagent).order_by(Reagent.name.asc()).all()
    for reagent in reagents:
        usage = reagent_usage_map.get(
            reagent.name,
            _ReagentUsageBucket(
                estimated_monthly_consumption=0.0,
                actual_run_count=0,
                source_equipment=set(),
            ),
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
                source_equipment=sorted(usage["source_equipment"]),
                days_of_cover=days_of_cover,
            )
        )
    return MonthlyConsumptionDashboardResponse(month=f"{year:04d}-{month:02d}", items=items)


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
    return CriticalThresholdDashboardResponse(total_critical_reagents=len(items), items=items)


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


@router.get("/compliance-summary")
def compliance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(default=30, ge=1, le=366),
) -> dict:
    """Synthèse de conformité ISO 15189 sur la période.

    Couvre la validation, l'auto-validation (§5.8), les corrections de résultats,
    l'acquittement des valeurs critiques et la signature des comptes-rendus.
    Renvoie aussi des taux et un statut global (compliant / attention).
    """
    del current_user
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)

    base = db.query(Result).filter(
        Result.analysis_date >= start_date, Result.analysis_date <= end_date
    )
    total_results = base.with_entities(func.count(Result.id)).scalar() or 0
    validated = (
        base.with_entities(func.count(Result.id)).filter(Result.is_validated.is_(True)).scalar()
        or 0
    )
    auto_validated = (
        base.with_entities(func.count(Result.id))
        .filter(Result.is_auto_validated.is_(True))
        .scalar()
        or 0
    )
    critical_total = (
        base.with_entities(func.count(Result.id)).filter(Result.is_critical.is_(True)).scalar() or 0
    )
    critical_acked = (
        base.with_entities(func.count(Result.id))
        .filter(Result.is_critical.is_(True), Result.critical_ack_at.is_not(None))
        .scalar()
        or 0
    )

    amendments = (
        db.query(func.count(AuditEvent.id))
        .filter(
            AuditEvent.event_type == "result.amend",
            AuditEvent.created_at >= start_date,
            AuditEvent.created_at <= end_date,
        )
        .scalar()
        or 0
    )
    signed_reports = (
        db.query(func.count(ReportSignature.id))
        .filter(
            ReportSignature.signed_at >= start_date,
            ReportSignature.signed_at <= end_date,
            ReportSignature.revoked_at.is_(None),  # exclut les signatures révoquées
        )
        .scalar()
        or 0
    )

    def _rate(num: int, denom: int) -> float:
        return round((num / denom) * 100, 1) if denom else 0.0

    validation_rate = _rate(validated, total_results)
    critical_ack_rate = _rate(critical_acked, critical_total)
    auto_validation_rate = _rate(auto_validated, validated)

    # Statut global : conforme si validation ≥ 99 % et tous critiques acquittés
    pending_criticals = critical_total - critical_acked
    is_compliant = validation_rate >= 99.0 and pending_criticals == 0
    return {
        "period_days": days,
        "period_start": start_date.date().isoformat(),
        "period_end": end_date.date().isoformat(),
        "total_results": total_results,
        "validated_results": validated,
        "auto_validated_results": auto_validated,
        "critical_total": critical_total,
        "critical_acked": critical_acked,
        "pending_criticals": pending_criticals,
        "amendments": amendments,
        "signed_reports": signed_reports,
        "validation_rate_pct": validation_rate,
        "critical_ack_rate_pct": critical_ack_rate,
        "auto_validation_rate_pct": auto_validation_rate,
        "status": "compliant" if is_compliant else "attention",
    }


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _compliance_for_window(db: Session, start: datetime, end: datetime) -> dict:
    base = db.query(Result).filter(Result.analysis_date >= start, Result.analysis_date < end)
    total = base.with_entities(func.count(Result.id)).scalar() or 0
    validated = (
        base.with_entities(func.count(Result.id)).filter(Result.is_validated.is_(True)).scalar()
        or 0
    )
    auto = (
        base.with_entities(func.count(Result.id))
        .filter(Result.is_auto_validated.is_(True))
        .scalar()
        or 0
    )
    crit_total = (
        base.with_entities(func.count(Result.id)).filter(Result.is_critical.is_(True)).scalar() or 0
    )
    crit_acked = (
        base.with_entities(func.count(Result.id))
        .filter(Result.is_critical.is_(True), Result.critical_ack_at.is_not(None))
        .scalar()
        or 0
    )

    def _rate(num: int, denom: int) -> float:
        return round((num / denom) * 100, 1) if denom else 0.0

    return {
        "total_results": total,
        "validated_results": validated,
        "validation_rate_pct": _rate(validated, total),
        "auto_validation_rate_pct": _rate(auto, validated),
        "critical_ack_rate_pct": _rate(crit_acked, crit_total),
    }


@router.get("/compliance-trend")
def compliance_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    months: int = Query(default=12, ge=1, le=36),
    drift_threshold_pct: float = Query(default=99.0, ge=0, le=100),
) -> dict:
    """Série mensuelle des indicateurs de conformité + détection de dérive.

    Renvoie une entrée par mois (du plus ancien au plus récent) et signale les
    mois dont le taux de validation passe sous ``drift_threshold_pct``.
    """
    del current_user
    today = datetime.now(UTC).replace(tzinfo=None)
    year, month = today.year, today.month
    # Construit la liste des (year, month) sur la fenêtre, du plus ancien au plus récent
    periods: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(months):
        periods.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    periods.reverse()

    series: list[dict] = []
    drift_months: list[str] = []
    for yy, mm in periods:
        start, end = _month_bounds(yy, mm)
        metrics = _compliance_for_window(db, start, end)
        label = f"{yy:04d}-{mm:02d}"
        entry = {"month": label, **metrics}
        # Dérive : uniquement si des résultats existent ce mois-là
        if metrics["total_results"] > 0 and metrics["validation_rate_pct"] < drift_threshold_pct:
            entry["drift"] = True
            drift_months.append(label)
        else:
            entry["drift"] = False
        series.append(entry)

    return {
        "months": months,
        "drift_threshold_pct": drift_threshold_pct,
        "drift_months": drift_months,
        "has_drift": bool(drift_months),
        "series": series,
    }


@router.get(
    "/compliance-report",
    summary="Rapport de conformité HTML (imprimable / export PDF navigateur)",
    responses={200: {"content": {"text/html": {}}}},
)
def compliance_html_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(default=30, ge=1, le=366),
) -> Response:
    """Document HTML standalone du rapport de conformité (impression / PDF navigateur)."""
    del current_user
    summary = compliance_summary(db=db, current_user=None, days=days)  # type: ignore[arg-type]
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    status_color = "#0f766e" if summary["status"] == "compliant" else "#b45309"
    rows = "".join(
        f"<tr><td>{html_escape(str(label))}</td>"
        f"<td style='text-align:right'>{html_escape(str(value))}</td></tr>"
        for label, value in (
            ("Résultats (période)", summary["total_results"]),
            ("Validés", summary["validated_results"]),
            ("Auto-validés (§5.8)", summary["auto_validated_results"]),
            ("Taux de validation", f"{summary['validation_rate_pct']} %"),
            ("Taux d'auto-validation", f"{summary['auto_validation_rate_pct']} %"),
            ("Valeurs critiques", summary["critical_total"]),
            ("Critiques acquittées", summary["critical_acked"]),
            ("Critiques en attente", summary["pending_criticals"]),
            ("Taux d'acquittement critique", f"{summary['critical_ack_rate_pct']} %"),
            ("Corrections (amend)", summary["amendments"]),
            ("Comptes-rendus signés", summary["signed_reports"]),
        )
    )
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport de conformité ISO 15189</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:720px;margin:32px auto;color:#1f2937;}}
 h1{{font-size:20px;}} table{{width:100%;border-collapse:collapse;margin-top:16px;}}
 td{{padding:7px 10px;border-bottom:1px solid #e5e7eb;}}
 .badge{{display:inline-block;padding:4px 12px;border-radius:14px;color:#fff;font-weight:600;background:{status_color};}}
 .meta{{color:#6b7280;font-size:13px;}}
</style></head><body>
<h1>Rapport de conformité — ISO 15189</h1>
<p class="meta">Période : {html_escape(str(summary["period_start"]))} → {html_escape(str(summary["period_end"]))} ({html_escape(str(days))} jours) · Généré le {html_escape(generated)}</p>
<p>Statut global : <span class="badge">{html_escape(str(summary["status"]).upper())}</span></p>
<table><tbody>{rows}</tbody></table>
<p class="meta" style="margin-top:24px;">Document généré par RuggyLab OS — à viser par le responsable qualité.</p>
</body></html>"""
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": 'inline; filename="rapport-conformite.html"'},
    )


DEFAULT_CRITICAL_ACK_TARGET_MINUTES = 30


def _critical_compliance_rows(
    db: Session,
    start_date: datetime,
    end_date: datetime,
    user: User,
    target_minutes: int = DEFAULT_CRITICAL_ACK_TARGET_MINUTES,
    exam_code: str | None = None,
    unit: str | None = None,
) -> list[dict]:
    query = (
        db.query(Result)
        .outerjoin(Sample, Sample.id == Result.sample_id)
        .outerjoin(Patient, Patient.id == Sample.patient_id)
    )
    query = apply_result_patient_scope(query, user, patient_joined=True).filter(
        Result.is_critical.is_(True),
        Result.analysis_date >= start_date,
        Result.analysis_date <= end_date,
    )
    if exam_code:
        query = query.filter(func.upper(Result.exam_code) == exam_code.upper())
    if unit:
        query = query.filter(func.upper(Patient.unit) == unit.upper())
    results = query.order_by(Result.analysis_date.desc(), Result.id.desc()).all()
    user_ids = {result.critical_ack_by_id for result in results if result.critical_ack_by_id}
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_by_id = {user.id: user for user in users}
    rows = []
    for result in results:
        sample = result.sample
        patient = sample.patient if sample else None
        ack_user = (
            user_by_id.get(result.critical_ack_by_id)
            if result.critical_ack_by_id is not None
            else None
        )
        ack_delay_minutes = None
        elapsed_minutes = None
        if result.critical_ack_at and result.analysis_date:
            ack_delay_minutes = round(
                (result.critical_ack_at - result.analysis_date).total_seconds() / 60,
                1,
            )
        elif result.analysis_date:
            elapsed_minutes = round((end_date - result.analysis_date).total_seconds() / 60, 1)
        delay_for_compliance = (
            ack_delay_minutes if ack_delay_minutes is not None else elapsed_minutes
        )
        within_target = delay_for_compliance is not None and delay_for_compliance <= target_minutes
        compliance_status = (
            "dans_delai"
            if within_target
            else "hors_delai"
            if delay_for_compliance is not None
            else "non_mesurable"
        )
        rows.append(
            {
                "result_id": result.id,
                "analysis_date": result.analysis_date.isoformat() if result.analysis_date else None,
                "critical_ack_at": result.critical_ack_at.isoformat()
                if result.critical_ack_at
                else None,
                "ack_delay_minutes": ack_delay_minutes,
                "elapsed_minutes": elapsed_minutes,
                "target_minutes": target_minutes,
                "within_target": within_target,
                "compliance_status": compliance_status,
                "status": "pris_en_charge" if result.critical_ack_at else "en_attente",
                "sample_barcode": sample.barcode if sample else None,
                "patient_ipp": patient.ipp_unique_id if patient else None,
                "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
                "unit": patient.unit if patient else None,
                "exam_code": result.exam_code,
                "ack_by_id": ack_user.id if ack_user else None,
                "ack_by": ack_user.full_name or ack_user.username if ack_user else None,
            }
        )
    return rows


def _critical_compliance_breakdown(rows: list[dict], field: str) -> list[dict]:
    counters: dict[str, dict[str, int]] = {}
    for row in rows:
        key = str(row.get(field) or "Non renseigné")
        entry = counters.setdefault(key, {"total": 0, "late": 0, "pending": 0})
        entry["total"] += 1
        if row["compliance_status"] == "hors_delai":
            entry["late"] += 1
        if row["status"] == "en_attente":
            entry["pending"] += 1
    return [
        {"label": key, **value}
        for key, value in sorted(
            counters.items(),
            key=lambda item: (item[1]["late"], item[1]["pending"], item[1]["total"], item[0]),
            reverse=True,
        )
    ][:8]


@router.get("/critical-compliance")
def critical_compliance_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
    days: int = Query(default=30, ge=1, le=366),
    target_minutes: int = Query(default=DEFAULT_CRITICAL_ACK_TARGET_MINUTES, ge=1, le=1440),
    exam_code: str | None = Query(default=None, min_length=1, max_length=50),
    unit: str | None = Query(default=None, min_length=1, max_length=100),
) -> dict:
    """Rapport conformité des valeurs critiques : attente, délai, taux de prise en charge."""
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    rows = _critical_compliance_rows(
        db,
        start_date,
        end_date,
        current_user,
        target_minutes,
        exam_code,
        unit,
    )
    handled = [row for row in rows if row["critical_ack_at"]]
    pending = [row for row in rows if not row["critical_ack_at"]]
    late = [row for row in rows if row["compliance_status"] == "hors_delai"]
    on_time = [row for row in rows if row["compliance_status"] == "dans_delai"]
    delays = [
        float(row["ack_delay_minutes"]) for row in handled if row["ack_delay_minutes"] is not None
    ]
    return {
        "period_days": days,
        "period_start": start_date.date().isoformat(),
        "period_end": end_date.date().isoformat(),
        "target_minutes": target_minutes,
        "filters": {"exam_code": exam_code, "unit": unit},
        "critical_total": len(rows),
        "critical_handled": len(handled),
        "critical_pending": len(pending),
        "critical_on_time": len(on_time),
        "critical_late": len(late),
        "ack_rate_pct": round((len(handled) / len(rows)) * 100, 1) if rows else 0.0,
        "on_time_rate_pct": round((len(on_time) / len(rows)) * 100, 1) if rows else 0.0,
        "avg_ack_delay_minutes": round(sum(delays) / len(delays), 1) if delays else None,
        "max_ack_delay_minutes": max(delays) if delays else None,
        "summary": {
            "message": (
                f"{len(late)} valeur(s) critique(s) hors délai cible sur {len(rows)} "
                f"sur {days} jour(s), seuil {target_minutes} min."
            ),
            "top_exams": _critical_compliance_breakdown(rows, "exam_code"),
            "by_unit": _critical_compliance_breakdown(rows, "unit"),
        },
        "rows": rows,
    }


@router.get("/critical-compliance/export.csv")
def critical_compliance_export_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(forbid_accountant),
    days: int = Query(default=30, ge=1, le=366),
    target_minutes: int = Query(default=DEFAULT_CRITICAL_ACK_TARGET_MINUTES, ge=1, le=1440),
    exam_code: str | None = Query(default=None, min_length=1, max_length=50),
    unit: str | None = Query(default=None, min_length=1, max_length=100),
) -> Response:
    """Export CSV du rapport conformité des valeurs critiques."""
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    rows = _critical_compliance_rows(
        db,
        start_date,
        end_date,
        current_user,
        target_minutes,
        exam_code,
        unit,
    )
    output = StringIO()
    writer = csv.writer(output)
    columns = [
        "result_id",
        "analysis_date",
        "critical_ack_at",
        "ack_delay_minutes",
        "elapsed_minutes",
        "target_minutes",
        "compliance_status",
        "status",
        "ack_by",
        "sample_barcode",
        "patient_ipp",
        "patient_name",
        "unit",
        "exam_code",
    ]
    writer.writerow(columns)
    for row in rows:
        writer.writerow([sanitize_csv_cell(row.get(column) or "") for column in columns])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="critical-compliance.csv"'},
    )


@router.get(
    "/qc-report",
    summary="Rapport QC mensuel HTML (imprimable / export PDF navigateur)",
    responses={200: {"content": {"text/html": {}}}},
)
def qc_html_report(
    year: int = Query(default=None, ge=2020, le=2099),
    month: int = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """Retourne un document HTML standalone avec les graphes Levey-Jennings SVG
    et le tableau de synthese mensuel. Ouvrir dans un onglet et imprimer / Ctrl+P."""
    del current_user
    today = dt.date.today()
    effective_year = year if year is not None else today.year
    effective_month = month if month is not None else today.month
    html = build_qc_html_report(effective_year, effective_month, db)
    filename = f"qc-rapport-{effective_year}-{effective_month:02d}.html"
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

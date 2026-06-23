import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import AuditEvent, Equipment, ReportSignature, Result, Sample, User
from app.schemas.fhir import FHIRDiagnosticReport
from app.schemas.pagination import PaginationMeta, ResultListResponse
from app.schemas.patient import PatientRead
from app.schemas.result import (
    CriticalAckBatchRequest,
    CriticalAckBatchResponse,
    ResultAmend,
    ResultClinicalAuditEvent,
    ResultCockpitItem,
    ResultCreate,
    ResultDetailRead,
    ResultHistoryItem,
    ResultHistoryRead,
    ResultRead,
)
from app.schemas.sample import SampleRead
from app.services.audit import log_audit_event
from app.services.auto_validator import try_auto_validate
from app.services.critical_checker import check_critical
from app.services.delta_checker import check_delta
from app.services.fhir_builder import build_diagnostic_report
from app.services.inventory import InsufficientStockError, consume_reagents_for_result
from app.services.patient_access import (
    apply_result_patient_scope,
    can_access_result,
)
from app.services.reference_checker import compute_flags
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/results")


def _get_accessible_result_or_error(db: Session, result_id: int, user: User) -> Result:
    """404 si le résultat n'existe pas ; 403 si son patient est hors périmètre RBAC."""
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable.")
    if not can_access_result(user, result):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès au résultat hors de votre périmètre.",
        )
    return result


_NON_ANALYTIC_KEYS = {"manual_entry_by", "entry_timestamp", "calibration", "overall_flags"}


def _result_analytes(result: Result) -> set[str]:
    return {
        key
        for key in (result.data_points or {})
        if isinstance(key, str) and key not in _NON_ANALYTIC_KEYS
    }


def _numeric_data_point(raw: object) -> float | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, dict):
        value = raw.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _sample_read(sample: Sample | None) -> SampleRead | None:
    return SampleRead.model_validate(sample) if sample is not None else None


def _patient_read(sample: Sample | None) -> PatientRead | None:
    if sample is None or sample.patient is None:
        return None
    return PatientRead.model_validate(sample.patient)


def _critical_value_alert_payload(result: Result) -> dict:
    sample = result.sample
    patient = sample.patient if sample else None
    patient_name = f"{patient.last_name} {patient.first_name}".strip() if patient else None
    return {
        "result_id": result.id,
        "sample_id": result.sample_id,
        "sample_barcode": sample.barcode if sample else None,
        "exam_code": result.exam_code,
        "patient_id": patient.id if patient else None,
        "patient_ipp": patient.ipp_unique_id if patient else None,
        "patient_name": patient_name,
        "occurred_at": (result.tech_validated_at or result.analysis_date).isoformat()
        if (result.tech_validated_at or result.analysis_date)
        else None,
        "message": "Valeur critique techniquement validée - prise en charge immédiate requise.",
    }


@router.get("", response_model=ResultListResponse)
def list_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sample_id: int | None = Query(default=None, ge=1),
    equipment_id: int | None = Query(default=None, ge=1),
    is_critical: bool | None = Query(default=None),
    is_validated: bool | None = Query(default=None),
) -> ResultListResponse:
    query = db.query(Result)
    if sample_id is not None:
        query = query.filter(Result.sample_id == sample_id)
    if equipment_id is not None:
        query = query.filter(Result.equipment_id == equipment_id)
    if is_critical is not None:
        query = query.filter(Result.is_critical == is_critical)
    if is_validated is not None:
        query = query.filter(Result.is_validated == is_validated)
    # Cloisonnement RBAC : restreindre aux patients du périmètre de l'utilisateur
    query = apply_result_patient_scope(query, current_user)

    total = query.with_entities(func.count(Result.id)).scalar() or 0
    items = query.order_by(Result.id.desc()).offset(skip).limit(limit).all()
    return ResultListResponse(
        items=[ResultRead.model_validate(r) for r in items],
        meta=PaginationMeta.from_counts(total=total, skip=skip, limit=limit),
    )


@router.get("/cockpit", response_model=list[ResultCockpitItem])
def list_results_cockpit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(100, ge=1, le=200),
) -> list[ResultCockpitItem]:
    """Liste enrichie pour le cockpit : résultat + échantillon + patient."""
    # Cloisonnement RBAC + eager-load échantillon/patient (évite le N+1)
    base = db.query(Result).options(joinedload(Result.sample).joinedload(Sample.patient))
    query = apply_result_patient_scope(base, current_user)
    results = query.order_by(Result.id.desc()).limit(limit).all()
    return [
        ResultCockpitItem(
            result=ResultRead.model_validate(result),
            sample=_sample_read(result.sample),
            patient=_patient_read(result.sample),
        )
        for result in results
    ]


@router.patch("/ack-critical-batch", response_model=CriticalAckBatchResponse)
def ack_critical_batch(
    payload: CriticalAckBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CriticalAckBatchResponse:
    """Prendre en charge plusieurs valeurs critiques affichées dans le cockpit."""
    acknowledged: list[int] = []
    skipped: dict[int, str] = {}
    unique_ids = list(dict.fromkeys(payload.result_ids))
    results = db.query(Result).filter(Result.id.in_(unique_ids)).all()
    result_by_id = {result.id: result for result in results}
    now = utcnow_naive()

    for result_id in unique_ids:
        result = result_by_id.get(result_id)
        if result is None:
            skipped[result_id] = "introuvable"
            continue
        if not can_access_result(current_user, result):
            skipped[result_id] = "hors périmètre"
            continue
        if not result.is_critical:
            skipped[result_id] = "non critique"
            continue
        if result.critical_ack_at is not None:
            skipped[result_id] = "déjà pris en charge"
            continue
        result.critical_ack_at = now
        result.critical_ack_by_id = current_user.id
        acknowledged.append(result.id)
        log_audit_event(
            db,
            user=current_user,
            event_type="result.critical_ack",
            entity_type="result",
            entity_id=str(result.id),
            payload={"source": "batch"},
        )

    db.commit()
    return CriticalAckBatchResponse(acknowledged=acknowledged, skipped=skipped)


@router.get("/{result_id}", response_model=ResultRead)
def get_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    return _get_accessible_result_or_error(db, result_id, current_user)


@router.get("/{result_id}/bioref")
def get_result_bioref(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Interprétation bioref complémentaire d'un résultat (par composant si panel).

    N'affecte pas les flags ni le statut critique ; couche additive.
    """
    from app.services.code_mapping_service import interpret_result_bioref

    result = _get_accessible_result_or_error(db, result_id, current_user)
    outcome = interpret_result_bioref(db, result)
    if outcome is None:
        return {"mapped": False, "exam_code": result.exam_code}
    return {"mapped": True, **outcome}


@router.get("/{result_id}/detail", response_model=ResultDetailRead)
def get_result_detail(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ResultDetailRead:
    """Détail cockpit d'un résultat avec contexte patient, échantillon et bioref."""
    from app.services.code_mapping_service import interpret_result_bioref

    result = _get_accessible_result_or_error(db, result_id, current_user)

    bioref_outcome = interpret_result_bioref(db, result)
    bioref = (
        {"mapped": False, "exam_code": result.exam_code}
        if bioref_outcome is None
        else {"mapped": True, **bioref_outcome}
    )
    sample = result.sample
    return ResultDetailRead(
        result=ResultRead.model_validate(result),
        sample=_sample_read(sample),
        patient=_patient_read(sample),
        bioref=bioref,
    )


@router.get("/{result_id}/history", response_model=ResultHistoryRead)
def get_result_history(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(5, ge=1, le=20),
) -> ResultHistoryRead:
    """Antériorités comparables du même patient pour la fiche résultat."""
    result = _get_accessible_result_or_error(db, result_id, current_user)

    patient_id = result.sample.patient_id if result.sample else None
    if patient_id is None:
        return ResultHistoryRead(result_id=result.id, patient_id=None, exam_code=result.exam_code)

    query = (
        db.query(Result)
        .join(Sample, Result.sample_id == Sample.id)
        .options(joinedload(Result.sample))  # eager-load pour _sample_read (évite le N+1)
        .filter(Sample.patient_id == patient_id, Result.id != result.id)
    )
    if result.exam_code:
        query = query.filter(Result.exam_code == result.exam_code)

    candidates = query.order_by(Result.analysis_date.desc(), Result.id.desc()).limit(50).all()
    current_analytes = _result_analytes(result)
    current_points = result.data_points or {}
    items: list[ResultHistoryItem] = []
    for previous in candidates:
        shared_analytes = sorted(current_analytes & _result_analytes(previous))
        if not result.exam_code and not shared_analytes:
            continue
        previous_points = previous.data_points or {}
        deltas = {}
        for analyte in shared_analytes:
            current_value = _numeric_data_point(current_points.get(analyte))
            previous_value = _numeric_data_point(previous_points.get(analyte))
            if current_value is not None and previous_value is not None:
                deltas[analyte] = round(current_value - previous_value, 4)
        items.append(
            ResultHistoryItem(
                result=ResultRead.model_validate(previous),
                sample=_sample_read(previous.sample),
                shared_analytes=shared_analytes,
                delta_from_current=deltas,
            )
        )
        if len(items) >= limit:
            break

    return ResultHistoryRead(
        result_id=result.id,
        patient_id=patient_id,
        exam_code=result.exam_code,
        items=items,
    )


@router.get("/{result_id}/clinical-audit", response_model=list[ResultClinicalAuditEvent])
def get_result_clinical_audit(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(20, ge=1, le=100),
) -> list[ResultClinicalAuditEvent]:
    """Timeline clinique/audit liée à un résultat."""
    _get_accessible_result_or_error(db, result_id, current_user)
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "result", AuditEvent.entity_id == str(result_id))
        .order_by(AuditEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [
        ResultClinicalAuditEvent(
            id=event.id,
            created_at=event.created_at,
            event_type=event.event_type,
            username=event.user.username if event.user else None,
            payload=event.payload,
        )
        for event in events
    ]


@router.get(
    "/{result_id}/fhir",
    response_model=FHIRDiagnosticReport,
    summary="Export NFS result as FHIR R4 DiagnosticReport",
    responses={
        200: {
            "content": {"application/fhir+json": {}},
            "description": "FHIR R4 DiagnosticReport (self-contained, with Patient and Observations)",
        },
        404: {"description": "Result not found"},
    },
)
def get_result_fhir(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONResponse:
    """Return a FHIR R4 DiagnosticReport for the requested result."""
    result = _get_accessible_result_or_error(db, result_id, current_user)

    report = build_diagnostic_report(result)
    return JSONResponse(
        content=report.model_dump(exclude_none=True),
        media_type="application/fhir+json",
    )


@router.post("", response_model=ResultRead, status_code=status.HTTP_201_CREATED)
def create_result(
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    sample = db.query(Sample).filter(Sample.id == payload.sample_id).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Echantillon introuvable pour l'identifiant {payload.sample_id}.",
        )

    if payload.equipment_id is not None:
        equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipement introuvable pour l'identifiant {payload.equipment_id}.",
            )

    result_data = payload.model_dump(exclude_none=True)
    result_data["validator_id"] = current_user.id
    result_data["is_validated"] = True
    # Auto-detect critical values against configured thresholds (OR with manual flag)
    result_data["is_critical"] = payload.is_critical or check_critical(payload.data_points, db)
    # Resolve patient for delta-check and reference flags
    patient = sample.patient
    patient_id = patient.id if patient else None
    patient_sex = patient.sex if patient else None
    patient_birth = patient.birth_date if patient else None
    # Delta-check: detect abrupt inter-result variation
    delta_exceeded, delta_analytes = check_delta(payload.data_points, patient_id, db)
    result_data["delta_exceeded"] = delta_exceeded
    result_data["delta_analytes"] = delta_analytes if delta_analytes else None
    # Reference flags: HH/H/N/L/LL per analyte
    computed_flags = compute_flags(payload.data_points, patient_sex, patient_birth, db)
    result_data["flags"] = computed_flags if computed_flags else None
    # Suivi TAT — pré-remplissage des horodatages de phase (modifiable ensuite)
    now = utcnow_naive()
    analysis_dt = result_data.get("analysis_date") or now
    result_data.setdefault("collected_at", sample.collection_date)
    result_data.setdefault("received_at", sample.received_date)
    # « Enregistrement » = point de départ du TAT (prélèvement par défaut)
    result_data.setdefault("registered_at", sample.collection_date or sample.received_date or now)
    result_data.setdefault("analysis_finished_at", analysis_dt)
    # Le résultat est créé validé → validation biologique horodatée maintenant
    result_data["bio_validated_at"] = now
    result_data["tech_validated_at"] = now
    result = Result(**result_data)
    db.add(result)
    db.flush()
    try:
        consume_reagents_for_result(
            db,
            result=result,
            user=current_user,
            source="result.create",
        )
    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stock reactif insuffisant pour valider ce resultat.",
                "items": [item.__dict__ for item in exc.items],
            },
        ) from exc
    # Auto-validation ISO 15189 §5.8
    try_auto_validate(result, db)
    # Interprétation bioref complémentaire (additive, ne touche pas flags/critique).
    # Best-effort : ne doit jamais empêcher la création du résultat.
    with contextlib.suppress(Exception):
        from app.services.code_mapping_service import apply_bioref_to_result

        apply_bioref_to_result(db, result)
    db.commit()
    db.refresh(result)
    # Push temps-réel : alerte immédiate si critique ou delta dépassé
    if result.is_critical or result.delta_exceeded:
        from app.services.notification_bus import publish_alert_event

        if result.is_critical:
            publish_alert_event("critical_value_alert", **_critical_value_alert_payload(result))
        if result.delta_exceeded:
            publish_alert_event("delta", result_id=result.id)
    # Alerte pré-analytique NON bloquante : aspect d'échantillon faussant un analyte.
    from app.services.preanalytic import interference_warning

    _warn = interference_warning(sample.aspect, result.data_points)
    if _warn:
        from app.services.notification_bus import publish_alert_event

        publish_alert_event(
            "preanalytic_interference",
            result_id=result.id,
            sample_id=sample.id,
            aspect=sample.aspect,
            message=_warn,
        )
    return result


@router.patch("/{result_id}/amend", response_model=ResultRead)
def amend_result(
    result_id: int,
    payload: ResultAmend,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> Result:
    """Corriger les data_points d'un résultat validé (réservé officier/admin).

    Recalcule automatiquement flags, delta-check et statut critique.
    Crée une entrée d'audit avec l'état avant/après et le motif obligatoire.
    Réinitialise l'auto-validation (le résultat corrigé doit être requalifié).
    Si un compte-rendu a été signé, sa signature est révoquée (les données
    signées ne correspondent plus) — intégrité ISO 15189.
    """
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable.")

    # Snapshot de l'ancien état pour l'audit
    old_data_points = result.data_points
    old_is_critical = result.is_critical

    # Intégrité : révoquer toute signature de compte-rendu existante
    signature_revoked = False
    signature = db.query(ReportSignature).filter(ReportSignature.result_id == result_id).first()
    if signature and signature.revoked_at is None:
        signature.revoked_at = utcnow_naive()
        signature.revocation_reason = (
            f"Données corrigées (amend) — motif: {payload.amendment_reason}"
        )
        signature_revoked = True

    # Mise à jour des données
    result.data_points = payload.data_points
    result.amendment_reason = payload.amendment_reason

    # Recalcul critique
    result.is_critical = check_critical(payload.data_points, db)

    # Recalcul delta
    patient = result.sample.patient if result.sample else None
    patient_id = patient.id if patient else None
    patient_sex = patient.sex if patient else None
    patient_birth = patient.birth_date if patient else None
    delta_exceeded, delta_analytes = check_delta(payload.data_points, patient_id, db)
    result.delta_exceeded = delta_exceeded
    result.delta_analytes = delta_analytes if delta_analytes else None

    # Recalcul flags
    computed_flags = compute_flags(payload.data_points, patient_sex, patient_birth, db)
    result.flags = computed_flags if computed_flags else None

    # Réinitialisation auto-validation (les données ont changé)
    result.is_auto_validated = False
    result.auto_validated_at = None

    # Tentative d'auto-revalidation sur le résultat corrigé
    try_auto_validate(result, db)

    # Audit trail
    audit = AuditEvent(
        user_id=current_user.id,
        event_type="result.amend",
        entity_type="result",
        entity_id=str(result_id),
        payload=json.dumps(
            {
                "amendment_reason": payload.amendment_reason,
                "old_data_points": old_data_points,
                "new_data_points": payload.data_points,
                "old_is_critical": old_is_critical,
                "new_is_critical": result.is_critical,
                "is_auto_validated": result.is_auto_validated,
                "signature_revoked": signature_revoked,
            }
        ),
    )
    db.add(audit)
    db.commit()
    db.refresh(result)
    return result


@router.patch("/{result_id}/ack-critical", response_model=ResultRead)
def ack_critical(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    """Acknowledge a critical value — records operator and timestamp."""
    result = _get_accessible_result_or_error(db, result_id, current_user)
    if not result.is_critical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce résultat n'est pas marqué critique.",
        )
    if result.critical_ack_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Valeur critique déjà acquittée.",
        )
    result.critical_ack_at = utcnow_naive()
    result.critical_ack_by_id = current_user.id
    log_audit_event(
        db,
        user=current_user,
        event_type="result.critical_ack",
        entity_type="result",
        entity_id=str(result.id),
        payload={"source": "single"},
    )
    db.commit()
    db.refresh(result)
    return result

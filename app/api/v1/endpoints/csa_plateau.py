"""Administration du futur connecteur CSA PLATEAU (sans transport réseau)."""

import datetime as dt

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import AuditEvent, CsaExamMapping, Result, User
from app.schemas.csa_plateau import (
    CSAContractTestRequest,
    CSAContractTestResponse,
    CSAExamMappingCreate,
    CSAExamMappingRead,
    CSAIntegrationStatus,
    CSAResultPushResponse,
    CSASyncSummary,
)
from app.services.audit import log_audit_event
from app.services.csa_plateau import (
    get_csa_plateau_adapter,
    import_prescription_event,
    result_payload_for_csa,
)

router = APIRouter(prefix="/csa-plateau")


@router.get("/status", response_model=CSAIntegrationStatus)
def csa_plateau_status(_: User = Depends(require_admin)) -> CSAIntegrationStatus:
    """État non sensible du socle. L'URL configurée n'est jamais divulguée."""

    return get_csa_plateau_adapter().status()


@router.post("/contract-test", response_model=CSAContractTestResponse)
def test_csa_plateau_contract(
    payload: CSAContractTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CSAContractTestResponse:
    """Valide le contrat localement; ne déclenche jamais d'appel externe."""

    key = get_csa_plateau_adapter().contract_key(payload)
    already_tested = (
        db.query(AuditEvent.id)
        .filter(
            AuditEvent.event_type == "csa_plateau.contract_test",
            AuditEvent.entity_type == "csa_contract",
            AuditEvent.entity_id == key,
        )
        .first()
        is not None
    )
    if not already_tested:
        log_audit_event(
            db,
            user=current_user,
            event_type="csa_plateau.contract_test",
            entity_type="csa_contract",
            entity_id=key,
            payload={
                "mode": "local_contract_validation",
                "exam_count": len(payload.prescription.exams),
                "network_call_performed": False,
                "patient_exchange_performed": False,
            },
        )
        db.commit()

    return CSAContractTestResponse(
        valid=True,
        idempotency_key=key,
        replayed=already_tested,
    )


@router.get("/exam-mappings", response_model=list[CSAExamMappingRead])
def list_exam_mappings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[CsaExamMapping]:
    return db.query(CsaExamMapping).order_by(CsaExamMapping.csa_exam_code).all()


@router.post("/exam-mappings", response_model=CSAExamMappingRead, status_code=201)
def create_exam_mapping(
    payload: CSAExamMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CsaExamMapping:
    csa_code = payload.csa_exam_code.strip().upper()
    existing = (
        db.query(CsaExamMapping)
        .filter(
            CsaExamMapping.csa_exam_code == csa_code,
            CsaExamMapping.ruggylab_exam_code
            == payload.ruggylab_exam_code.strip().upper(),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Cette paire de mapping CSA existe déjà.")
    mapping = CsaExamMapping(
        csa_exam_code=csa_code,
        ruggylab_exam_code=payload.ruggylab_exam_code.strip().upper(),
        active=payload.active,
    )
    db.add(mapping)
    log_audit_event(
        db,
        user=current_user,
        event_type="csa_plateau.exam_mapping.create",
        entity_type="csa_exam_mapping",
        payload={"csa_exam_code": csa_code, "ruggylab_exam_code": mapping.ruggylab_exam_code},
    )
    db.commit()
    db.refresh(mapping)
    return mapping


@router.post("/sync/prescriptions", response_model=CSASyncSummary)
def sync_prescriptions(
    changed_since: dt.datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CSASyncSummary:
    adapter = get_csa_plateau_adapter()
    try:
        events = adapter.pull_prescriptions(changed_since, limit)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    imported = replayed = 0
    rejected: list[dict] = []
    for event in events:
        try:
            outcome, order_id = import_prescription_event(
                db, event, created_by_id=current_user.id
            )
            if outcome == "imported":
                imported += 1
                adapter.push_event(
                    "labo_receipts",
                    str((event.get("payload") or {}).get("prescription_id") or event.get("item_id")),
                    {
                        "prescription_id": (event.get("payload") or {}).get("prescription_id"),
                        "ruggylab_order_id": order_id,
                        "statut": "recu",
                        "recu_le": dt.datetime.now(dt.UTC).isoformat(),
                    },
                )
            else:
                replayed += 1
            db.commit()
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            db.rollback()
            rejected.append(
                {
                    "event_key": event.get("event_key"),
                    "reason": str(exc),
                }
            )
    log_audit_event(
        db,
        user=current_user,
        event_type="csa_plateau.prescriptions.sync",
        entity_type="csa_sync",
        payload={
            "received": len(events),
            "imported": imported,
            "replayed": replayed,
            "rejected_count": len(rejected),
        },
    )
    db.commit()
    return CSASyncSummary(
        received=len(events), imported=imported, replayed=replayed, rejected=rejected
    )


@router.post("/results/{result_id}/push", response_model=CSAResultPushResponse)
def push_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CSAResultPushResponse:
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Résultat introuvable.")
    try:
        source_item_id, payload = result_payload_for_csa(db, result)
        event_key = get_csa_plateau_adapter().push_event(
            "labo_resultats", source_item_id, payload
        )
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log_audit_event(
        db,
        user=current_user,
        event_type="csa_plateau.result.push",
        entity_type="result",
        entity_id=str(result.id),
        payload={"external_event_key": event_key, "exam_code": result.exam_code},
    )
    db.commit()
    return CSAResultPushResponse(result_id=result.id, external_event_key=event_key)

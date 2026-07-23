"""Ingestion robuste des résultats automate via middleware ASTM."""

from __future__ import annotations

import contextlib
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Result
from app.schemas.analyzer import AnalyzerResultIngest
from app.services.audit import log_audit_event
from app.services.auto_validator import try_auto_validate
from app.services.critical_checker import check_critical
from app.services.delta_checker import check_delta
from app.services.inventory import InsufficientStockError, consume_reagents_for_result
from app.services.reference_checker import compute_flags
from app.services.sample_workflow import (
    CancelledSampleError,
    ensure_sample_processable,
    lock_sample_by_barcode,
)
from app.utils.datetime_utils import utcnow_naive


class AnalyzerIngestionError(ValueError):
    """Erreur métier contrôlée pour ingestion automate."""


def _lock_idempotency_key(db: Session, key: str) -> None:
    """Sérialise une même clé d'ingestion pendant la transaction PostgreSQL."""
    if db.get_bind().dialect.name != "postgresql":
        return
    lock_id = int.from_bytes(bytes.fromhex(key)[:8], byteorder="big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(lock_id)))


def analyzer_idempotency_key(payload: AnalyzerResultIngest) -> str:
    """Construit une clé stable pour éviter les doublons de rejeu middleware."""
    if payload.message_id:
        base = f"{payload.analyzer_id}|{payload.message_id}"
    elif payload.raw_message_hash:
        base = f"{payload.analyzer_id}|{payload.sample_barcode}|{payload.raw_message_hash}"
    else:
        canonical = json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        base = f"{payload.analyzer_id}|{canonical}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _existing_result_id(db: Session, key: str) -> int | None:
    existing = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "analyzer.result_ingest",
            AuditEvent.entity_type == "analyzer_message",
            AuditEvent.entity_id == key,
        )
        .first()
    )
    if not existing or not existing.payload:
        return None
    with contextlib.suppress(Exception):
        payload = json.loads(existing.payload)
        result_id = payload.get("result_id")
        if isinstance(result_id, int):
            return result_id
    return None


def ingest_analyzer_result(db: Session, payload: AnalyzerResultIngest) -> dict:
    """Crée un résultat depuis un middleware automate, avec idempotence."""
    key = analyzer_idempotency_key(payload)
    _lock_idempotency_key(db, key)
    duplicate_result_id = _existing_result_id(db, key)
    if duplicate_result_id is not None:
        duplicate_result = db.query(Result).filter(Result.id == duplicate_result_id).first()
        if duplicate_result is None:
            raise AnalyzerIngestionError(
                "Piste d'idempotence automate incoherente: resultat d'origine introuvable."
            )
        persisted_sample = duplicate_result.sample
        return {
            "status": "duplicate",
            "result_id": duplicate_result_id,
            "sample_id": persisted_sample.id,
            "sample_barcode": persisted_sample.barcode,
            "idempotency_key": key,
            "message": "Message automate deja integre.",
        }

    sample = lock_sample_by_barcode(db, payload.sample_barcode)
    if sample is None:
        raise AnalyzerIngestionError(
            f"Echantillon introuvable pour le code-barres {payload.sample_barcode}."
        )
    try:
        ensure_sample_processable(sample)
    except CancelledSampleError as exc:
        raise AnalyzerIngestionError(str(exc)) from exc

    patient = sample.patient
    patient_id = patient.id if patient else None
    patient_sex = patient.sex if patient else None
    patient_birth = patient.birth_date if patient else None
    now = utcnow_naive()
    analysis_date = payload.analysis_date or now

    delta_exceeded, delta_analytes = check_delta(payload.data_points, patient_id, db)
    flags = compute_flags(payload.data_points, patient_sex, patient_birth, db)
    result = Result(
        sample_id=sample.id,
        analysis_date=analysis_date,
        data_points=payload.data_points,
        is_validated=True,
        is_critical=check_critical(payload.data_points, db),
        delta_exceeded=delta_exceeded,
        delta_analytes=delta_analytes if delta_analytes else None,
        flags=flags if flags else None,
        exam_code=payload.exam_code,
        registered_at=sample.collection_date or sample.received_date or now,
        collected_at=sample.collection_date,
        received_at=sample.received_date,
        analysis_finished_at=analysis_date,
        tech_validated_at=now,
        bio_validated_at=now,
    )
    db.add(result)
    db.flush()

    try:
        consume_reagents_for_result(db, result=result, user=None, source="analyzer.ingest")
    except InsufficientStockError as exc:
        raise AnalyzerIngestionError(
            "Stock reactif insuffisant pour integrer ce resultat automate."
        ) from exc

    try_auto_validate(result, db)

    with contextlib.suppress(Exception):
        from app.services.code_mapping_service import apply_bioref_to_result

        apply_bioref_to_result(db, result)

    log_audit_event(
        db,
        user=None,
        event_type="analyzer.result_ingest",
        entity_type="analyzer_message",
        entity_id=key,
        payload={
            "result_id": result.id,
            "sample_id": sample.id,
            "sample_barcode": sample.barcode,
            "analyzer_id": payload.analyzer_id,
            "message_id": payload.message_id,
            "exam_code": payload.exam_code,
            "raw_message_hash": payload.raw_message_hash,
        },
    )
    db.commit()
    db.refresh(result)

    if result.is_critical or result.delta_exceeded:
        from app.services.notification_bus import publish_alert_event

        if result.is_critical:
            publish_alert_event(
                "critical_value_alert",
                result_id=result.id,
                sample_id=result.sample_id,
                sample_barcode=sample.barcode,
                exam_code=result.exam_code,
                patient_id=patient.id if patient else None,
                patient_ipp=patient.ipp_unique_id if patient else None,
                patient_name=f"{patient.last_name} {patient.first_name}".strip()
                if patient
                else None,
                occurred_at=(result.tech_validated_at or result.analysis_date).isoformat(),
                message="Valeur critique techniquement validee par automate - prise en charge immediate requise.",
            )
        if result.delta_exceeded:
            publish_alert_event("delta", result_id=result.id)

    return {
        "status": "created",
        "result_id": result.id,
        "sample_id": sample.id,
        "sample_barcode": sample.barcode,
        "idempotency_key": key,
        "message": "Resultat automate integre avec succes.",
    }

"""Concurrence annulation/résultat nécessitant PostgreSQL réel."""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi import HTTPException

import app.services.analyzer_ingestion as analyzer_ingestion_service
from app.api.v1.endpoints.samples import update_sample
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, Patient, Result, Sample, User, UserRole
from app.schemas.analyzer import AnalyzerResultIngest
from app.schemas.sample import SampleUpdate
from app.services.analyzer_ingestion import analyzer_idempotency_key, ingest_analyzer_result

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide le verrou de ligne échantillon sous PostgreSQL.",
)


def test_result_and_cancellation_are_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        user = User(
            username=f"preanalytic_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        patient = Patient(
            ipp_unique_id=f"PREANALYTIC-PG-{suffix}",
            first_name="Synthetic",
            last_name="Cancellation",
            birth_date=dt.date(1990, 1, 1),
            sex="F",
        )
        sample = Sample(
            barcode=f"PREANALYTIC-PG-S-{suffix}",
            patient=patient,
            status="Recu",
        )
        setup.add_all([user, patient, sample])
        setup.commit()
        user_id = user.id
        patient_id = patient.id
        sample_id = sample.id
        barcode = sample.barcode

    payload = AnalyzerResultIngest(
        analyzer_id=f"preanalytic-analyzer-{suffix}",
        message_id=f"preanalytic-message-{suffix}",
        sample_barcode=barcode,
        exam_code="SYNTHETIC",
        data_points={"SYNTHETIC": 1.0},
    )
    idempotency_key = analyzer_idempotency_key(payload)
    result_holds_sample_lock = threading.Event()
    release_result = threading.Event()
    original_check_delta = analyzer_ingestion_service.check_delta

    def pause_after_sample_lock(*args: Any, **kwargs: Any) -> tuple[bool, dict]:
        result_holds_sample_lock.set()
        assert release_result.wait(timeout=5)
        return original_check_delta(*args, **kwargs)

    monkeypatch.setattr(analyzer_ingestion_service, "check_delta", pause_after_sample_lock)

    def ingest() -> dict:
        with SessionLocal() as db:
            return ingest_analyzer_result(db, payload)

    def cancel() -> int:
        with SessionLocal() as db:
            current_user = db.get(User, user_id)
            assert current_user is not None
            try:
                update_sample(
                    sample_id,
                    SampleUpdate(status="Annule"),
                    db,
                    current_user,
                )
            except HTTPException as exc:
                return exc.status_code
            return 200

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        result_future = executor.submit(ingest)
        assert result_holds_sample_lock.wait(timeout=5)
        cancellation_future = executor.submit(cancel)
        time.sleep(0.25)
        assert not cancellation_future.done(), "l'annulation n'a pas attendu le verrou échantillon"

        release_result.set()
        assert result_future.result(timeout=10)["status"] == "created"
        assert cancellation_future.result(timeout=10) == 409

        with SessionLocal() as verification:
            persisted = verification.get(Sample, sample_id)
            assert persisted is not None
            assert persisted.status == "Recu"
            assert verification.query(Result).filter(Result.sample_id == sample_id).count() == 1
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "analyzer.result_ingest",
                    AuditEvent.entity_id == idempotency_key,
                )
                .count()
                == 1
            )
    finally:
        release_result.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "analyzer.result_ingest",
                AuditEvent.entity_id == idempotency_key,
            ).delete(synchronize_session=False)
            cleanup.query(Result).filter(Result.sample_id == sample_id).delete(
                synchronize_session=False
            )
            stored_sample = cleanup.get(Sample, sample_id)
            if stored_sample is not None:
                cleanup.delete(stored_sample)
            cleanup.flush()
            stored_patient = cleanup.get(Patient, patient_id)
            if stored_patient is not None:
                cleanup.delete(stored_patient)
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()

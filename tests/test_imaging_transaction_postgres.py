"""Preuve PostgreSQL d'idempotence concurrente des jobs d'imagerie."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints.imaging import submit_malaria_analysis
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, MalariaAnalysisJob, Result, Sample, User, UserRole
from app.services import malaria_ai

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide le verrou de résultat sous PostgreSQL.",
)


def test_concurrent_malaria_submissions_create_one_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as setup:
        user = User(
            username=f"imaging_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        sample = Sample(
            barcode=f"IMAGING-PG-{suffix}",
            status="Recu",
        )
        setup.add_all([user, sample])
        setup.flush()
        result = Result(
            sample_id=sample.id,
            data_points={},
            image_url=f"synthetic/microscopy/{suffix}.jpg",
            is_validated=False,
            is_critical=False,
        )
        setup.add(result)
        setup.commit()
        user_id = user.id
        sample_id = sample.id
        result_id = result.id

    first_enqueue_holds_lock = threading.Event()
    release_first_enqueue = threading.Event()
    original_log_audit_event = malaria_ai.log_audit_event

    def pause_enqueue(*args: Any, **kwargs: Any) -> AuditEvent:
        if kwargs.get("event_type") == "malaria.analysis.enqueue":
            first_enqueue_holds_lock.set()
            assert release_first_enqueue.wait(timeout=5)
        return original_log_audit_event(*args, **kwargs)

    monkeypatch.setattr(malaria_ai, "log_audit_event", pause_enqueue)

    def submit() -> int:
        with SessionLocal() as db:
            current_user = db.get(User, user_id)
            assert current_user is not None
            job = submit_malaria_analysis(
                result_id,
                BackgroundTasks(),
                db,
                current_user,
            )
            return job.id

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first = executor.submit(submit)
        assert first_enqueue_holds_lock.wait(timeout=5)
        duplicate = executor.submit(submit)
        time.sleep(0.25)
        assert not duplicate.done(), "la seconde soumission n'a pas attendu le verrou résultat"

        release_first_enqueue.set()
        first_id = first.result(timeout=10)
        assert duplicate.result(timeout=10) == first_id

        with SessionLocal() as verification:
            assert (
                verification.query(MalariaAnalysisJob)
                .filter(MalariaAnalysisJob.result_id == result_id)
                .count()
                == 1
            )
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "malaria.analysis.enqueue",
                    AuditEvent.user_id == user_id,
                )
                .count()
                == 1
            )
    finally:
        release_first_enqueue.set()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "malaria.analysis.enqueue",
                AuditEvent.user_id == user_id,
            ).delete(synchronize_session=False)
            cleanup.query(MalariaAnalysisJob).filter(
                MalariaAnalysisJob.result_id == result_id
            ).delete(synchronize_session=False)
            stored_result = cleanup.get(Result, result_id)
            if stored_result is not None:
                cleanup.delete(stored_result)
            stored_sample = cleanup.get(Sample, sample_id)
            if stored_sample is not None:
                cleanup.delete(stored_sample)
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()

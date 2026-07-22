"""Régressions de concurrence clinique nécessitant PostgreSQL réel."""

from __future__ import annotations

import datetime as dt
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.api.v1.endpoints.exam_orders import collect_exam_order
from app.db.session import SessionLocal, engine
from app.models import (
    AuditEvent,
    ExamOrder,
    ExamOrderItem,
    Patient,
    Sample,
    User,
    UserRole,
)
from app.schemas.exam_order import ExamOrderCollect

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide SELECT FOR UPDATE et exige PostgreSQL.",
)


def test_r1_competing_sample_attachments_are_serialized() -> None:
    suffix = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        user = User(
            username=f"safety_pg_{suffix}",
            hashed_password="synthetic-not-used",
            role=UserRole.ADMIN,
            is_active=True,
        )
        patient = Patient(
            ipp_unique_id=f"SAFETY-PG-{suffix}",
            first_name="Synthetic",
            last_name="Concurrency",
            birth_date=dt.date(1990, 1, 1),
            sex="F",
        )
        first_sample = Sample(
            barcode=f"SAFETY-PG-A-{suffix}", patient=patient, status="Recu"
        )
        second_sample = Sample(
            barcode=f"SAFETY-PG-B-{suffix}", patient=patient, status="Recu"
        )
        order = ExamOrder(
            patient=patient,
            created_by_id=None,
            status="prescribed",
            items=[ExamOrderItem(exam_code="NFS", status="pending")],
        )
        db.add_all([user, patient, first_sample, second_sample, order])
        db.flush()
        order.created_by_id = user.id
        db.commit()
        user_id = user.id
        patient_id = patient.id
        order_id = order.id
        first_sample_id = first_sample.id
        second_sample_id = second_sample.id

    session_a = SessionLocal()
    lock_query_started = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    second_attempt = None
    worker_thread_id: int | None = None

    def observe_lock_query(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        if threading.get_ident() == worker_thread_id and "FOR UPDATE" in statement.upper():
            lock_query_started.set()

    event.listen(engine, "before_cursor_execute", observe_lock_query)

    def attach_second_sample() -> int:
        nonlocal worker_thread_id
        worker_thread_id = threading.get_ident()
        with SessionLocal() as session_b:
            user_b = session_b.get(User, user_id)
            assert user_b is not None
            try:
                collect_exam_order(
                    order_id,
                    ExamOrderCollect(sample_id=second_sample_id),
                    session_b,
                    user_b,
                )
            except HTTPException as exc:
                return exc.status_code
            return 200

    try:
        user_a = session_a.get(User, user_id)
        assert user_a is not None
        locked_order = (
            session_a.query(ExamOrder)
            .filter(ExamOrder.id == order_id)
            .with_for_update()
            .one()
        )
        assert locked_order.sample_id is None

        second_attempt = executor.submit(attach_second_sample)
        assert lock_query_started.wait(timeout=5)
        time.sleep(0.25)
        assert not second_attempt.done(), "la seconde transaction n'a pas attendu le verrou"

        first_response = collect_exam_order(
            order_id,
            ExamOrderCollect(sample_id=first_sample_id),
            session_a,
            user_a,
        )
        assert first_response.sample_id == first_sample_id
        assert second_attempt.result(timeout=5) == 409

        with SessionLocal() as verification:
            persisted = verification.get(ExamOrder, order_id)
            assert persisted is not None
            assert persisted.sample_id == first_sample_id
            assert (
                verification.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "exam_order.collect",
                    AuditEvent.entity_id == str(order_id),
                )
                .count()
                == 1
            )
    finally:
        session_a.rollback()
        session_a.close()
        executor.shutdown(wait=True, cancel_futures=True)
        event.remove(engine, "before_cursor_execute", observe_lock_query)
        with SessionLocal() as cleanup:
            cleanup.query(AuditEvent).filter(
                AuditEvent.event_type == "exam_order.collect",
                AuditEvent.entity_id == str(order_id),
            ).delete(synchronize_session=False)
            stored_order = cleanup.get(ExamOrder, order_id)
            if stored_order is not None:
                cleanup.delete(stored_order)
            for sample_id in (first_sample_id, second_sample_id):
                stored_sample = cleanup.get(Sample, sample_id)
                if stored_sample is not None:
                    cleanup.delete(stored_sample)
            cleanup.flush()
            stored_patient = cleanup.get(Patient, patient_id)
            if stored_patient is not None:
                cleanup.delete(stored_patient)
            cleanup.flush()
            stored_user = cleanup.get(User, user_id)
            if stored_user is not None:
                cleanup.delete(stored_user)
            cleanup.commit()

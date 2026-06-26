from __future__ import annotations

import datetime as dt

from app.db.session import SessionLocal
from app.models import ReportDeliveryOutbox, ReportSnapshot
from app.services.report_delivery_outbox import process_report_delivery_outbox
from app.utils.datetime_utils import utcnow_naive


def _snapshot(db) -> ReportSnapshot:
    snapshot = ReportSnapshot(
        result_id=1,
        version_number=1,
        status="provisional",
        audience="clinician",
        schema_version="1.0",
        content_snapshot={"result": {"id": 1}},
        pdf_sha256="a" * 64,
        verification_token_hash="b" * 64,
        verification_path="/api/v1/reports/verify/test",
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def test_internal_report_delivery_event_is_processed(client) -> None:
    del client
    db = SessionLocal()
    try:
        snapshot = _snapshot(db)
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel="internal",
            status="pending",
            idempotency_key="report:1:released:internal",
            payload={"snapshot_id": snapshot.id},
            next_attempt_at=utcnow_naive() - dt.timedelta(seconds=1),
        )
        db.add(event)
        db.commit()

        result = process_report_delivery_outbox(db)

        db.refresh(event)
        assert result.processed == 1
        assert event.status == "processed"
        assert event.processed_at is not None
        assert event.last_error is None
    finally:
        db.close()


def test_unconfigured_channel_retries_then_dead_letters(client) -> None:
    del client
    db = SessionLocal()
    try:
        snapshot = _snapshot(db)
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel="email",
            status="pending",
            idempotency_key="report:2:released:email",
            payload={"snapshot_id": snapshot.id},
            attempt_count=1,
            next_attempt_at=utcnow_naive() - dt.timedelta(seconds=1),
        )
        db.add(event)
        db.commit()

        result = process_report_delivery_outbox(db, max_attempts=2)

        db.refresh(event)
        assert result.dead_lettered == 1
        assert event.status == "dead_letter"
        assert "Canal de diffusion non configure" in (event.last_error or "")
    finally:
        db.close()


def test_external_dispatcher_can_process_channel(client) -> None:
    del client
    db = SessionLocal()
    seen: list[int] = []
    try:
        snapshot = _snapshot(db)
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel="fhir",
            status="pending",
            idempotency_key="report:3:released:fhir",
            payload={"snapshot_id": snapshot.id},
            next_attempt_at=utcnow_naive() - dt.timedelta(seconds=1),
        )
        db.add(event)
        db.commit()

        result = process_report_delivery_outbox(
            db,
            dispatchers={"fhir": lambda item: seen.append(item.id)},
        )

        db.refresh(event)
        assert result.processed == 1
        assert seen == [event.id]
        assert event.status == "processed"
    finally:
        db.close()

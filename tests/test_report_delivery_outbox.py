from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.db.session import SessionLocal
from app.models import Patient, ReportDeliveryOutbox, ReportSnapshot, Result, Sample
from app.services.report_delivery_outbox import process_report_delivery_outbox
from app.utils.datetime_utils import utcnow_naive


def _auth_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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


def _result_with_snapshot(db) -> tuple[Result, ReportSnapshot]:
    patient = Patient(
        ipp_unique_id="IPP-DELIVERY-001",
        first_name="Delivery",
        last_name="Patient",
        birth_date=dt.date(1984, 1, 1),
        sex="F",
    )
    db.add(patient)
    db.flush()
    sample = Sample(barcode="BAR-DELIVERY-001", patient_id=patient.id, status="Recu")
    db.add(sample)
    db.flush()
    result = Result(
        sample_id=sample.id,
        data_points={"WBC": {"value": 6.1, "unit": "10^9/L", "status": "NORMAL"}},
        is_critical=False,
        is_validated=True,
    )
    db.add(result)
    db.flush()
    snapshot = ReportSnapshot(
        result_id=result.id,
        version_number=1,
        status="final",
        audience="clinician",
        schema_version="1.0",
        content_snapshot={"result": {"id": result.id}},
        pdf_sha256="c" * 64,
        verification_token_hash="d" * 64,
        verification_path="/api/v1/reports/verify/test-delivery",
    )
    db.add(snapshot)
    db.flush()
    return result, snapshot


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
        assert "Destinataire email non configure" in (event.last_error or "")
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


def test_patient_portal_channel_writes_snapshot_pdf(client, tmp_path: Path, monkeypatch) -> None:
    del client
    monkeypatch.setattr(
        "app.services.report_delivery_outbox.settings.REPORT_DELIVERY_OUTPUT_DIR",
        str(tmp_path),
    )
    db = SessionLocal()
    try:
        _, snapshot = _result_with_snapshot(db)
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel="patient_portal",
            status="pending",
            idempotency_key="report:4:released:patient_portal",
            payload={"snapshot_id": snapshot.id},
            next_attempt_at=utcnow_naive() - dt.timedelta(seconds=1),
        )
        db.add(event)
        db.commit()

        result = process_report_delivery_outbox(db)

        db.refresh(event)
        pdf_path = Path(event.payload["pdf_path"])
        assert result.processed == 1
        assert event.status == "processed"
        assert pdf_path.exists()
        assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    finally:
        db.close()


def test_fhir_channel_writes_diagnostic_report_json(client, tmp_path: Path, monkeypatch) -> None:
    del client
    monkeypatch.setattr(
        "app.services.report_delivery_outbox.settings.REPORT_DELIVERY_FHIR_DIR",
        str(tmp_path),
    )
    db = SessionLocal()
    try:
        result_model, snapshot = _result_with_snapshot(db)
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel="fhir",
            status="pending",
            idempotency_key="report:5:released:fhir",
            payload={"snapshot_id": snapshot.id},
            next_attempt_at=utcnow_naive() - dt.timedelta(seconds=1),
        )
        db.add(event)
        db.commit()

        result = process_report_delivery_outbox(db)

        db.refresh(event)
        fhir_path = Path(event.payload["fhir_path"])
        payload = fhir_path.read_text(encoding="utf-8")
        assert result.processed == 1
        assert event.status == "processed"
        assert fhir_path.exists()
        assert '"resourceType": "DiagnosticReport"' in payload
        assert f'"value": "{result_model.id}"' in payload
    finally:
        db.close()


def test_release_endpoint_accepts_filesystem_and_fhir_channels(
    client,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.report_delivery_outbox.settings.REPORT_DELIVERY_OUTPUT_DIR",
        str(tmp_path / "pdf"),
    )
    monkeypatch.setattr(
        "app.services.report_delivery_outbox.settings.REPORT_DELIVERY_FHIR_DIR",
        str(tmp_path / "fhir"),
    )
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-DELIVERY-UAT",
            "first_name": "Uat",
            "last_name": "Delivery",
            "birth_date": "1984-01-01",
            "sex": "F",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BAR-DELIVERY-UAT", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "data_points": {"WBC": {"value": 6.1, "unit": "10^9/L", "status": "NORMAL"}},
            "is_critical": False,
        },
    ).json()

    release = client.post(
        f"/api/v1/reports/results/{result['id']}/release",
        headers=headers,
        json={"audience": "clinician", "delivery_channels": ["filesystem", "fhir"]},
    )
    assert release.status_code == 201, release.text

    db = SessionLocal()
    try:
        processed = process_report_delivery_outbox(db)
        events = (
            db.query(ReportDeliveryOutbox)
            .filter(ReportDeliveryOutbox.report_snapshot_id == release.json()["id"])
            .order_by(ReportDeliveryOutbox.channel)
            .all()
        )
        assert processed.processed == 2
        assert [event.channel for event in events] == ["fhir", "filesystem"]
        assert all(event.status == "processed" for event in events)
        assert Path(events[0].payload["fhir_path"]).exists()
        assert Path(events[1].payload["pdf_path"]).exists()
    finally:
        db.close()

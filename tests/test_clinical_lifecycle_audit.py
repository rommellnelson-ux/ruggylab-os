"""Traçabilité atomique des mutations du cycle clinique principal."""

from __future__ import annotations

import json
import uuid
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import exam_orders as exam_orders_endpoint
from app.api.v1.endpoints import patients as patients_endpoint
from app.api.v1.endpoints import results as results_endpoint
from app.api.v1.endpoints import samples as samples_endpoint
from app.db.session import SessionLocal
from app.models import AuditEvent, ExamOrder, Patient, Result, Sample


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_patient(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"AUDIT-P-{suffix}",
            "first_name": "Synthetic",
            "last_name": "Audit",
            "birth_date": "1990-01-01",
            "sex": "F",
            "unit": "synthetic-unit",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _create_sample(
    client: TestClient,
    headers: dict[str, str],
    *,
    patient_id: int,
    suffix: str,
) -> tuple[int, str]:
    barcode = f"AUDIT-S-{suffix}"
    response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"]), barcode


def _create_order(
    client: TestClient,
    headers: dict[str, str],
    *,
    patient_id: int,
) -> int:
    response = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={
            "patient_id": patient_id,
            "priority": "routine",
            "exams": [{"exam_code": "SYNTHETIC-AUDIT"}],
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _event(event_type: str, entity_id: int) -> AuditEvent:
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == event_type,
                AuditEvent.entity_id == str(entity_id),
            )
            .one_or_none()
        )
        assert event is not None
        db.expunge(event)
        return event


def _fail_audit(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic audit failure")


def test_core_clinical_mutations_emit_minimal_audit_events(client: TestClient) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]

    patient_id = _create_patient(client, headers, suffix)
    sample_id, barcode = _create_sample(
        client,
        headers,
        patient_id=patient_id,
        suffix=suffix,
    )
    order_id = _create_order(client, headers, patient_id=patient_id)

    sample_update = client.patch(
        f"/api/v1/samples/{sample_id}",
        headers=headers,
        json={"status": "En cours", "aspect": "conforme"},
    )
    assert sample_update.status_code == 200, sample_update.text

    result_response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "exam_code": "SYNTHETIC-AUDIT",
            "data_points": {"SYNTHETIC": 1.0},
            "is_critical": False,
        },
    )
    assert result_response.status_code == 201, result_response.text
    result_id = int(result_response.json()["id"])

    order_update = client.patch(
        f"/api/v1/exam-orders/{order_id}",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert order_update.status_code == 200, order_update.text

    patient_event = _event("patient.create", patient_id)
    sample_create_event = _event("sample.create", sample_id)
    sample_update_event = _event("sample.update", sample_id)
    result_event = _event("result.create", result_id)
    order_create_event = _event("exam_order.create", order_id)
    order_update_event = _event("exam_order.status.update", order_id)

    assert json.loads(patient_event.payload or "{}") == {"unit": "synthetic-unit"}
    assert json.loads(sample_create_event.payload or "{}") == {
        "patient_id": patient_id,
        "status": "Recu",
    }
    assert json.loads(sample_update_event.payload or "{}") == {
        "fields": ["aspect", "status"],
        "old_status": "Recu",
        "new_status": "En cours",
        "old_aspect": None,
        "new_aspect": "conforme",
    }
    assert json.loads(result_event.payload or "{}") == {
        "sample_id": sample_id,
        "exam_code": "SYNTHETIC-AUDIT",
        "is_critical": False,
        "is_auto_validated": False,
    }
    assert json.loads(order_create_event.payload or "{}") == {
        "patient_id": patient_id,
        "priority": "routine",
        "item_count": 1,
    }
    assert json.loads(order_update_event.payload or "{}") == {
        "old_status": "prescribed",
        "requested_status": "cancelled",
    }

    serialized_payloads = " ".join(
        event.payload or ""
        for event in (
            patient_event,
            sample_create_event,
            sample_update_event,
            result_event,
            order_create_event,
            order_update_event,
        )
    )
    assert "Synthetic" not in serialized_payloads
    assert "Audit" not in serialized_payloads
    assert barcode not in serialized_payloads
    assert "data_points" not in serialized_payloads


def test_patient_creation_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    monkeypatch.setattr(patients_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "ipp_unique_id": f"AUDIT-FAIL-P-{suffix}",
                "first_name": "Synthetic",
                "last_name": "Rollback",
                "birth_date": "1990-01-01",
                "sex": "F",
            },
        )

    with SessionLocal() as db:
        assert (
            db.query(Patient)
            .filter(Patient.ipp_unique_id == f"AUDIT-FAIL-P-{suffix}")
            .one_or_none()
            is None
        )


def test_sample_creation_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    patient_id = _create_patient(client, headers, suffix)
    barcode = f"AUDIT-FAIL-S-{suffix}"
    monkeypatch.setattr(samples_endpoint, "log_audit_event", _fail_audit, raising=False)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post(
            "/api/v1/samples",
            headers=headers,
            json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
        )

    with SessionLocal() as db:
        assert db.query(Sample).filter(Sample.barcode == barcode).one_or_none() is None


def test_sample_update_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    patient_id = _create_patient(client, headers, suffix)
    sample_id, _ = _create_sample(client, headers, patient_id=patient_id, suffix=suffix)
    monkeypatch.setattr(samples_endpoint, "log_audit_event", _fail_audit, raising=False)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.patch(
            f"/api/v1/samples/{sample_id}",
            headers=headers,
            json={"status": "En cours"},
        )

    with SessionLocal() as db:
        sample = db.get(Sample, sample_id)
        assert sample is not None
        assert sample.status == "Recu"


def test_standard_result_creation_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    patient_id = _create_patient(client, headers, suffix)
    sample_id, _ = _create_sample(client, headers, patient_id=patient_id, suffix=suffix)
    monkeypatch.setattr(results_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post(
            "/api/v1/results",
            headers=headers,
            json={
                "sample_id": sample_id,
                "exam_code": "SYNTHETIC-AUDIT",
                "data_points": {"SYNTHETIC": 1.0},
                "is_critical": False,
            },
        )

    with SessionLocal() as db:
        assert db.query(Result).filter(Result.sample_id == sample_id).count() == 0


def test_order_creation_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    patient_id = _create_patient(client, headers, suffix)
    monkeypatch.setattr(exam_orders_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post(
            "/api/v1/exam-orders",
            headers=headers,
            json={
                "patient_id": patient_id,
                "priority": "routine",
                "exams": [{"exam_code": "SYNTHETIC-AUDIT"}],
            },
        )

    with SessionLocal() as db:
        assert db.query(ExamOrder).filter(ExamOrder.patient_id == patient_id).count() == 0


def test_order_status_update_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    suffix = uuid.uuid4().hex[:12]
    patient_id = _create_patient(client, headers, suffix)
    order_id = _create_order(client, headers, patient_id=patient_id)
    monkeypatch.setattr(exam_orders_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.patch(
            f"/api/v1/exam-orders/{order_id}",
            headers=headers,
            json={"status": "cancelled"},
        )

    with SessionLocal() as db:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        assert order.status == "prescribed"

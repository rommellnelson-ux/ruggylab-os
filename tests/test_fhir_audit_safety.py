"""Traçabilité minimale et sans identifiant direct des exports FHIR cliniques."""

from __future__ import annotations

import json
import uuid
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import results as results_endpoint
from app.db.session import SessionLocal
from app.models import AuditEvent


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _clinical_record(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[int, int, str]:
    suffix = uuid.uuid4().hex[:10]
    ipp = f"FHIR-AUDIT-SYN-{suffix}"
    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": ipp,
            "first_name": "Synthetic",
            "last_name": suffix,
            "birth_date": "1980-01-01",
            "sex": "F",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    patient_id = int(patient_response.json()["id"])
    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": f"FHIR-AUDIT-S-{suffix}",
            "patient_id": patient_id,
            "status": "Recu",
        },
    )
    assert sample_response.status_code == 201, sample_response.text
    result_response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_response.json()["id"],
            "data_points": {
                "SYNTHETIC": {
                    "value": 1.0,
                    "unit": "synthetic-unit",
                    "status": "NORMAL",
                }
            },
            "is_critical": False,
        },
    )
    assert result_response.status_code == 201, result_response.text
    return patient_id, int(result_response.json()["id"]), ipp


def _fail_audit(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic FHIR audit failure")


def test_result_fhir_export_is_audited(client: TestClient) -> None:
    headers = _auth(client)
    _, result_id, _ = _clinical_record(client, headers)

    response = client.get(f"/api/v1/results/{result_id}/fhir", headers=headers)

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "result.fhir.export",
                AuditEvent.entity_id == str(result_id),
            )
            .one()
        )
        assert json.loads(event.payload or "{}") == {"resource_type": "DiagnosticReport"}


def test_result_fhir_export_fails_closed_when_audit_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    _, result_id, _ = _clinical_record(client, headers)
    monkeypatch.setattr(results_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic FHIR audit failure"):
        client.get(f"/api/v1/results/{result_id}/fhir", headers=headers)

    with SessionLocal() as db:
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "result.fhir.export",
                AuditEvent.entity_id == str(result_id),
            )
            .count()
            == 0
        )


def test_patient_fhir_audit_omits_direct_patient_identifier(client: TestClient) -> None:
    headers = _auth(client)
    patient_id, _, ipp = _clinical_record(client, headers)

    response = client.get(f"/api/v1/patients/{patient_id}/fhir-bundle", headers=headers)

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "patient.fhir.export",
                AuditEvent.entity_id == str(patient_id),
            )
            .one()
        )
        assert json.loads(event.payload or "{}") == {"resource_count": 1}
        assert ipp not in (event.payload or "")

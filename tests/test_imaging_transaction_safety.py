"""Invariants transactionnels de la réservation d'imagerie synthétique."""

from __future__ import annotations

import json
import uuid
from typing import NoReturn, TypedDict, cast

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import imaging as imaging_endpoint
from app.db.session import SessionLocal
from app.models import AuditEvent, Result
from app.services import malaria_ai
from app.services.malaria_ai import MalariaPrediction


class _SampleData(TypedDict):
    id: int
    barcode: str


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _sample(
    client: TestClient,
    headers: dict[str, str],
    *,
    sample_status: str = "Recu",
) -> _SampleData:
    suffix = uuid.uuid4().hex[:10]
    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"IMAGING-SYN-{suffix}",
            "first_name": "Synthetic",
            "last_name": suffix,
            "birth_date": "1988-01-01",
            "sex": "F",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    barcode = f"IMAGING-SYN-S-{suffix}"
    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": barcode,
            "patient_id": patient_response.json()["id"],
            "status": sample_status,
        },
    )
    assert sample_response.status_code == 201, sample_response.text
    return cast(
        _SampleData,
        {"id": int(sample_response.json()["id"]), "barcode": barcode},
    )


def _fail_audit(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic imaging audit failure")


def _fail_inference(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic-sensitive-imaging-location")


def test_cancelled_sample_cannot_reserve_microscope_result(client: TestClient) -> None:
    headers = _auth(client)
    sample = _sample(client, headers, sample_status="Annule")

    response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": sample["barcode"]},
    )

    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert db.query(Result).filter(Result.sample_id == sample["id"]).count() == 0
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "imaging.capture.reserve").count()
            == 0
        )


def test_imaging_reservation_audit_omits_barcode_and_path(client: TestClient) -> None:
    headers = _auth(client)
    sample = _sample(client, headers)

    response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": sample["barcode"]},
    )

    assert response.status_code == 201, response.text
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "imaging.capture.reserve",
                AuditEvent.entity_id == str(response.json()["result_id"]),
            )
            .one()
        )
        assert json.loads(event.payload or "{}") == {"sample_id": sample["id"]}
        assert sample["barcode"] not in (event.payload or "")
        assert response.json()["image_url"] not in (event.payload or "")


def test_imaging_reservation_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    sample = _sample(client, headers)
    monkeypatch.setattr(imaging_endpoint, "log_audit_event", _fail_audit)

    with pytest.raises(RuntimeError, match="synthetic imaging audit failure"):
        client.post(
            "/api/v1/imaging/capture-microscope",
            headers=headers,
            json={"sample_barcode": sample["barcode"]},
        )

    with SessionLocal() as db:
        assert db.query(Result).filter(Result.sample_id == sample["id"]).count() == 0
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "imaging.capture.reserve").count()
            == 0
        )


def test_malaria_audits_omit_image_path_and_raw_inference_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    sample = _sample(client, headers)
    capture_response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": sample["barcode"]},
    )
    assert capture_response.status_code == 201, capture_response.text
    result_id = int(capture_response.json()["result_id"])
    image_url = str(capture_response.json()["image_url"])

    enqueue_response = client.post(
        f"/api/v1/imaging/malaria/analyze/{result_id}",
        headers=headers,
    )
    assert enqueue_response.status_code == 202, enqueue_response.text
    job_id = int(enqueue_response.json()["id"])

    with SessionLocal() as db:
        enqueue_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "malaria.analysis.enqueue",
                AuditEvent.entity_id == str(job_id),
            )
            .one()
        )
        assert json.loads(enqueue_event.payload or "{}") == {"result_id": result_id}
        assert image_url not in (enqueue_event.payload or "")

    monkeypatch.setattr(malaria_ai.classifier, "predict", _fail_inference)
    process_response = client.post(
        f"/api/v1/imaging/malaria/jobs/{job_id}/process",
        headers=headers,
    )
    assert process_response.status_code == 200, process_response.text
    assert process_response.json()["status"] == "failed"
    assert process_response.json()["error_message"] == "RuntimeError"
    assert "synthetic-sensitive-imaging-location" not in process_response.text

    with SessionLocal() as db:
        failure_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "malaria.analysis.fail",
                AuditEvent.entity_id == str(job_id),
            )
            .one()
        )
        assert json.loads(failure_event.payload or "{}") == {
            "result_id": result_id,
            "error_type": "RuntimeError",
        }
        assert "synthetic-sensitive-imaging-location" not in (failure_event.payload or "")


def test_malaria_prediction_never_mutates_clinical_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    sample = _sample(client, headers)
    capture_response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": sample["barcode"]},
    )
    assert capture_response.status_code == 201, capture_response.text
    result_id = int(capture_response.json()["result_id"])
    enqueue_response = client.post(
        f"/api/v1/imaging/malaria/analyze/{result_id}",
        headers=headers,
    )
    assert enqueue_response.status_code == 202, enqueue_response.text
    job_id = int(enqueue_response.json()["id"])

    monkeypatch.setattr(
        malaria_ai.classifier,
        "predict",
        lambda _image_url: MalariaPrediction(label="positive", confidence=0.99),
    )
    process_response = client.post(
        f"/api/v1/imaging/malaria/jobs/{job_id}/process",
        headers=headers,
    )
    assert process_response.status_code == 200, process_response.text
    assert process_response.json()["status"] == "completed"
    assert process_response.json()["clinical_use"] == "non_clinical"
    assert process_response.json()["result_mutated"] is False

    with SessionLocal() as db:
        result = db.get(Result, result_id)
        assert result is not None
        assert result.data_points == {}
        assert result.is_critical is False
        assert result.is_validated is False

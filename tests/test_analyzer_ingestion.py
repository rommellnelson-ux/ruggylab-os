"""Tests — ingestion sécurisée des résultats automates."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import pytest

from app.core.config import settings


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sample(client, headers: dict[str, str]) -> str:
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"AN-{_uid()}",
            "first_name": "Auto",
            "last_name": "Mate",
            "birth_date": "1988-01-01",
            "sex": "M",
        },
    ).json()
    barcode = f"ASTM-{_uid()}"
    response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": barcode, "patient_id": patient["id"], "status": "Recu"},
    )
    assert response.status_code == 201, response.text
    return barcode


def _payload(barcode: str, message_id: str = "MSG-001") -> dict:
    return {
        "analyzer_id": "astm-unit-test",
        "message_id": message_id,
        "sample_barcode": barcode,
        "exam_code": "NFS",
        "data_points": {"HGB": {"value": 4.8, "unit": "g/dL"}},
        "raw_message_hash": hashlib.sha256(message_id.encode()).hexdigest(),
    }


def _reset_analyzer_settings() -> None:
    settings.ANALYZER_API_KEY = "test-analyzer-key"
    settings.ANALYZER_ALLOWED_IPS = []
    settings.ANALYZER_HMAC_SECRET = None
    settings.ANALYZER_SIGNATURE_MAX_SKEW_SECONDS = 300


@pytest.fixture(autouse=True)
def analyzer_settings_guard():
    original = {
        "ANALYZER_API_KEY": settings.ANALYZER_API_KEY,
        "ANALYZER_ALLOWED_IPS": list(settings.ANALYZER_ALLOWED_IPS),
        "ANALYZER_HMAC_SECRET": settings.ANALYZER_HMAC_SECRET,
        "ANALYZER_SIGNATURE_MAX_SKEW_SECONDS": settings.ANALYZER_SIGNATURE_MAX_SKEW_SECONDS,
    }
    yield
    settings.ANALYZER_API_KEY = original["ANALYZER_API_KEY"]
    settings.ANALYZER_ALLOWED_IPS = original["ANALYZER_ALLOWED_IPS"]
    settings.ANALYZER_HMAC_SECRET = original["ANALYZER_HMAC_SECRET"]
    settings.ANALYZER_SIGNATURE_MAX_SKEW_SECONDS = original["ANALYZER_SIGNATURE_MAX_SKEW_SECONDS"]


def test_analyzer_ingest_requires_key(client) -> None:
    _reset_analyzer_settings()
    response = client.post("/api/v1/analyzer/results", json=_payload("NOPE"))
    assert response.status_code == 401


def test_analyzer_ingest_creates_result_and_is_idempotent(client) -> None:
    _reset_analyzer_settings()
    headers = _auth(client)
    barcode = _sample(client, headers)
    machine_headers = {"X-Analyzer-Key": settings.ANALYZER_API_KEY}
    payload = _payload(barcode, message_id=f"MSG-{_uid()}")

    first = client.post("/api/v1/analyzer/results", headers=machine_headers, json=payload)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["status"] == "created"
    assert first_body["result_id"] is not None

    second = client.post("/api/v1/analyzer/results", headers=machine_headers, json=payload)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["status"] == "duplicate"
    assert second_body["result_id"] == first_body["result_id"]


def test_analyzer_ingest_accepts_valid_hmac_signature(client) -> None:
    _reset_analyzer_settings()
    settings.ANALYZER_HMAC_SECRET = "hmac-secret-for-tests"
    headers = _auth(client)
    barcode = _sample(client, headers)
    payload = _payload(barcode, message_id=f"MSG-{_uid()}")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.ANALYZER_HMAC_SECRET.encode("utf-8"),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()

    response = client.post(
        "/api/v1/analyzer/results",
        headers={
            "X-Analyzer-Key": settings.ANALYZER_API_KEY,
            "X-Analyzer-Timestamp": timestamp,
            "X-Analyzer-Signature": signature,
            "Content-Type": "application/json",
        },
        content=body,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "created"

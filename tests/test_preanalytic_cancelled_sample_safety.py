"""Régressions de sécurité pré-analytique pour les échantillons annulés."""

from __future__ import annotations

import hashlib
import uuid
from typing import TypedDict, cast

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditEvent, ExamOrder, Result, Sample, StockMovement


class _SampleData(TypedDict):
    id: int
    barcode: str
    patient_id: int


def _admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _patient(client: TestClient, headers: dict[str, str]) -> int:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"CANCELLED-{suffix}",
            "first_name": "Synthetic",
            "last_name": suffix,
            "birth_date": "1988-01-01",
            "sex": "F",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _sample(
    client: TestClient,
    headers: dict[str, str],
    *,
    patient_id: int | None = None,
    sample_status: str = "Annule",
) -> _SampleData:
    resolved_patient_id = patient_id or _patient(client, headers)
    barcode = f"CANCELLED-S-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": barcode,
            "patient_id": resolved_patient_id,
            "status": sample_status,
        },
    )
    assert response.status_code == 201, response.text
    return cast(
        _SampleData,
        {
            "id": response.json()["id"],
            "barcode": barcode,
            "patient_id": resolved_patient_id,
        },
    )


def _assert_cancelled_without_result(sample_id: int) -> None:
    db = SessionLocal()
    try:
        sample = db.get(Sample, sample_id)
        assert sample is not None
        assert sample.status == "Annule"
        assert db.query(Result).filter(Result.sample_id == sample_id).count() == 0
        assert (
            db.query(StockMovement)
            .join(Result, StockMovement.result_id == Result.id)
            .filter(Result.sample_id == sample_id)
            .count()
            == 0
        )
    finally:
        db.close()


def _dh36_message(barcode: str, message_id: str, serial: str) -> str:
    return "\r".join(
        [
            f"MSH|^~\\&|{serial}|LAB|RUGGYLAB|LAB|20260429183000||ORU^R01|{message_id}|P|2.3",
            "PID|||SYNTHETIC-DH36||Cancelled^Sample",
            f"OBR|1||{barcode}|NFS^Numeration Formule Sanguine",
            "OBX|1|NM|WBC||6.1|10^9/L",
            "OBX|2|NM|RBC||4.7|10^12/L",
            "OBX|3|NM|HGB||132|g/L",
            "OBX|4|NM|HCT||40|%",
            "OBX|5|NM|MCV||86|fL",
            "OBX|6|NM|MCH||29|pg",
            "OBX|7|NM|MCHC||330|g/L",
            "OBX|8|NM|PLT||250|10^9/L",
        ]
    )


def test_cancelled_sample_rejects_standard_result_before_stock_or_audit(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": f"Cancelled equipment {uuid.uuid4().hex[:6]}",
            "serial_number": f"CANCELLED-EQ-{uuid.uuid4().hex[:8]}",
            "type": "Synthetic",
        },
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": f"Cancelled reagent {uuid.uuid4().hex[:8]}",
            "category": "synthetic",
            "unit": "mL",
            "current_stock": 10,
            "alert_threshold": 1,
        },
    ).json()
    ratio = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 2,
            "adjustment_factor": 1,
            "is_active": True,
        },
    )
    assert ratio.status_code == 201, ratio.text

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "equipment_id": equipment["id"],
            "exam_code": "SYNTHETIC",
            "data_points": {"SYNTHETIC": 1.0},
            "is_critical": False,
        },
    )

    assert response.status_code == 409
    _assert_cancelled_without_result(sample["id"])
    persisted_reagent = client.get(f"/api/v1/reagents/{reagent['id']}", headers=headers)
    assert persisted_reagent.status_code == 200
    assert persisted_reagent.json()["current_stock"] == 10
    db = SessionLocal()
    try:
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.entity_type == "result",
                AuditEvent.payload.contains(f'"sample_id": {sample["id"]}'),
            )
            .count()
            == 0
        )
    finally:
        db.close()


def test_cancelled_sample_rejects_precis_expert_result(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)
    serial = f"CANCELLED-PE-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Precis Expert", "serial_number": serial, "type": "POCT"},
    )

    response = client.post(
        "/api/v1/results/precis-expert",
        headers=headers,
        json={
            "sample_barcode": sample["barcode"],
            "equipment_serial": serial,
            "glucose_raw": 0.9,
            "cholesterol_raw": 1.5,
            "uric_acid_raw": 45,
            "lactate_raw": 1.2,
            "ketones_raw": 0.2,
        },
    )

    assert response.status_code == 409
    _assert_cancelled_without_result(sample["id"])


def test_cancelled_sample_rejects_poct_batch(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)
    serial = f"CANCELLED-POCT-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Precis Expert", "serial_number": serial, "type": "POCT"},
    )

    response = client.post(
        "/api/v1/results/poct-batch",
        headers=headers,
        json={
            "sample_barcode": sample["barcode"],
            "device_serial": serial,
            "items": [{"code": "GLU", "value": 0.9}],
        },
    )

    assert response.status_code == 409
    _assert_cancelled_without_result(sample["id"])


def test_cancelled_sample_rejects_qualitative_result(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)

    response = client.post(
        "/api/v1/results/qualitative",
        headers=headers,
        json={
            "sample_barcode": sample["barcode"],
            "category": "smear",
            "exam_code": "SYNTHETIC-SMEAR",
            "findings": {
                "is_negative": False,
                "observations": [{"organism": "Synthetic organism", "density": "+"}],
            },
        },
    )

    assert response.status_code == 409
    _assert_cancelled_without_result(sample["id"])


def test_cancelled_sample_rejects_analyzer_result(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)
    original = (
        settings.ANALYZER_API_KEY,
        list(settings.ANALYZER_ALLOWED_IPS),
        settings.ANALYZER_HMAC_SECRET,
    )
    settings.ANALYZER_API_KEY = "cancelled-sample-analyzer-key"
    settings.ANALYZER_ALLOWED_IPS = []
    settings.ANALYZER_HMAC_SECRET = None
    message_id = f"CANCELLED-MSG-{uuid.uuid4().hex[:8]}"
    try:
        response = client.post(
            "/api/v1/analyzer/results",
            headers={"X-Analyzer-Key": settings.ANALYZER_API_KEY},
            json={
                "analyzer_id": "synthetic-analyzer",
                "message_id": message_id,
                "sample_barcode": sample["barcode"],
                "exam_code": "SYNTHETIC",
                "data_points": {"SYNTHETIC": 1.0},
                "raw_message_hash": hashlib.sha256(message_id.encode()).hexdigest(),
            },
        )
    finally:
        (
            settings.ANALYZER_API_KEY,
            settings.ANALYZER_ALLOWED_IPS,
            settings.ANALYZER_HMAC_SECRET,
        ) = original

    assert response.status_code == 422
    _assert_cancelled_without_result(sample["id"])


def test_cancelled_sample_is_rejected_and_traced_by_dh36(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)
    serial = f"CANCELLED-DH36-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DH36", "serial_number": serial, "type": "Automate"},
    )

    response = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={
            "raw_message": _dh36_message(
                sample["barcode"],
                f"CANCELLED-DH36-MSG-{uuid.uuid4().hex[:8]}",
                serial,
            )
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "rejected"
    assert response.json()["result_id"] is None
    assert "annulé" in response.json()["rejection_reason"].lower()
    _assert_cancelled_without_result(sample["id"])


def test_cancelled_sample_cannot_be_collected_for_an_order(client: TestClient) -> None:
    headers = _admin(client)
    patient_id = _patient(client, headers)
    sample = _sample(client, headers, patient_id=patient_id)
    order_response = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={"patient_id": patient_id, "exams": [{"exam_code": "NFS"}]},
    )
    assert order_response.status_code == 201, order_response.text
    order_id = int(order_response.json()["id"])

    response = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": sample["id"]},
    )

    assert response.status_code == 409
    db = SessionLocal()
    try:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        assert order.sample_id is None
        assert order.status == "prescribed"
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "exam_order.collect",
                AuditEvent.entity_id == str(order_id),
            )
            .count()
            == 0
        )
    finally:
        db.close()


def test_collect_rejects_mismatched_sample_id_and_barcode(client: TestClient) -> None:
    headers = _admin(client)
    patient_id = _patient(client, headers)
    selected = _sample(
        client,
        headers,
        patient_id=patient_id,
        sample_status="Recu",
    )
    scanned = _sample(
        client,
        headers,
        patient_id=patient_id,
        sample_status="Recu",
    )
    order_response = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={"patient_id": patient_id, "exams": [{"exam_code": "NFS"}]},
    )
    assert order_response.status_code == 201, order_response.text
    order_id = int(order_response.json()["id"])

    response = client.post(
        f"/api/v1/exam-orders/{order_id}/collect",
        headers=headers,
        json={"sample_id": selected["id"], "barcode": scanned["barcode"]},
    )

    assert response.status_code == 422
    db = SessionLocal()
    try:
        order = db.get(ExamOrder, order_id)
        assert order is not None
        assert order.sample_id is None
        assert order.status == "prescribed"
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "exam_order.collect",
                AuditEvent.entity_id == str(order_id),
            )
            .count()
            == 0
        )
    finally:
        db.close()


def test_cancelled_sample_status_is_terminal(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers)

    response = client.patch(
        f"/api/v1/samples/{sample['id']}",
        headers=headers,
        json={"status": "Recu"},
    )

    assert response.status_code == 409
    _assert_cancelled_without_result(sample["id"])


def test_sample_with_result_cannot_be_cancelled(client: TestClient) -> None:
    headers = _admin(client)
    sample = _sample(client, headers, sample_status="Recu")
    result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "exam_code": "SYNTHETIC",
            "data_points": {"SYNTHETIC": 1.0},
            "is_critical": False,
        },
    )
    assert result.status_code == 201, result.text

    response = client.patch(
        f"/api/v1/samples/{sample['id']}",
        headers=headers,
        json={"status": "Annule"},
    )

    assert response.status_code == 409
    db = SessionLocal()
    try:
        persisted = db.get(Sample, sample["id"])
        assert persisted is not None
        assert persisted.status == "Recu"
        assert db.query(Result).filter(Result.sample_id == sample["id"]).count() == 1
    finally:
        db.close()

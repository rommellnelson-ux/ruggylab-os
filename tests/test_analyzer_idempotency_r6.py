"""Régressions locales du lot R6 — ingestion automate et DH36."""

from __future__ import annotations

import uuid

import pytest

from app.db.session import SessionLocal
from app.models import DH36InboundMessage, Equipment, Reagent, Result, Sample, StockMovement
from app.schemas.analyzer import AnalyzerResultIngest
from app.services.analyzer_ingestion import ingest_analyzer_result
from tests.equipment_registry_testkit import register_synthetic_qualified_equipment


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _auth(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _sample(client, headers: dict[str, str], *, prefix: str) -> dict:
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"{prefix}-IPP-{_uid()}",
            "first_name": "Synthetic",
            "last_name": "Analyzer",
            "birth_date": "1990-01-01",
            "sex": "F",
        },
    )
    assert patient.status_code == 201, patient.text
    response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": f"{prefix}-BAR-{_uid()}",
            "patient_id": patient.json()["id"],
            "status": "Recu",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dh36_message(barcode: str, message_id: str, serial: str) -> str:
    return "\r".join(
        [
            f"MSH|^~\\&|{serial}|LAB|RUGGYLAB|LAB|20260429183000||ORU^R01|{message_id}|P|2.3",
            "PID|||SYNTHETIC-R6||Analyzer^Safety",
            f"OBR|1||{barcode}||CBC",
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


def test_r6_analyzer_replay_reports_the_persisted_sample(client) -> None:
    headers = _auth(client)
    first_sample = _sample(client, headers, prefix="R6-A")
    other_sample = _sample(client, headers, prefix="R6-B")
    message_id = f"R6-MSG-{_uid()}"
    payload = AnalyzerResultIngest(
        analyzer_id="r6-synthetic-analyzer",
        message_id=message_id,
        sample_barcode=first_sample["barcode"],
        exam_code="NFS",
        data_points={"HGB": {"value": 13.2, "unit": "g/dL"}},
    )
    with SessionLocal() as db:
        _equipment, _interface, qualification = register_synthetic_qualified_equipment(
            db,
            asset_identifier=payload.analyzer_id,
            analyte_codes={"HGB"},
        )
        qualification_id = qualification.id

    with SessionLocal() as db:
        created = ingest_analyzer_result(db, payload)

    suspended = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/suspend",
        headers=headers,
        json={"reason": "incident"},
    )
    assert suspended.status_code == 200, suspended.text

    replay = payload.model_copy(update={"sample_barcode": other_sample["barcode"]})
    with SessionLocal() as db:
        duplicate = ingest_analyzer_result(db, replay)

    assert duplicate["status"] == "duplicate"
    assert duplicate["result_id"] == created["result_id"]
    assert duplicate["sample_id"] == first_sample["id"]
    assert duplicate["sample_barcode"] == first_sample["barcode"]
    with SessionLocal() as db:
        assert (
            db.query(Result).filter(Result.id == created["result_id"]).one().sample_id
            == first_sample["id"]
        )


def test_r6_dh36_stock_rejection_does_not_complete_sample(client) -> None:
    headers = _auth(client)
    sample = _sample(client, headers, prefix="R6-DH36")
    serial = f"R6-DH36-{_uid()}"
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DH36", "serial_number": serial, "type": "Automate"},
    )
    assert equipment.status_code == 201, equipment.text
    with SessionLocal() as db:
        stored_equipment = db.get(Equipment, equipment.json()["id"])
        assert stored_equipment is not None
        _equipment, _interface, qualification = register_synthetic_qualified_equipment(
            db,
            equipment=stored_equipment,
            asset_identifier=f"synthetic-dh36-{_uid()}",
            analyte_codes={"WBC", "RBC", "HGB", "HCT", "MCV", "MCH", "MCHC", "PLT"},
        )
        qualification_id = qualification.id
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": f"R6 DH36 Reagent {_uid()}",
            "category": "hematology",
            "unit": "L",
            "current_stock": 0.1,
            "alert_threshold": 0.05,
        },
    )
    assert reagent.status_code == 201, reagent.text
    ratio = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment.json()["id"],
            "reagent_id": reagent.json()["id"],
            "consumption_per_run": 0.25,
            "adjustment_factor": 1.0,
            "is_active": True,
        },
    )
    assert ratio.status_code == 201, ratio.text

    raw_message = _dh36_message(
        sample["barcode"],
        f"R6-DH36-MSG-{_uid()}",
        serial,
    )
    response = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={"raw_message": raw_message},
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["result_id"] is None
    assert "Stock reactif insuffisant" in response.json()["rejection_reason"]

    suspended = client.post(
        f"/api/v1/equipments/qualifications/{qualification_id}/suspend",
        headers=headers,
        json={"reason": "incident"},
    )
    assert suspended.status_code == 200, suspended.text
    duplicate = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={"raw_message": raw_message},
    )
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["message_id"] == response.json()["message_id"]

    with SessionLocal() as db:
        stored_sample = db.get(Sample, sample["id"])
        stored_reagent = db.get(Reagent, reagent.json()["id"])
        assert stored_sample is not None
        assert stored_sample.status == "Recu"
        assert stored_reagent is not None
        assert stored_reagent.current_stock == pytest.approx(0.1)
        assert db.query(Result).filter(Result.sample_id == sample["id"]).count() == 0
        assert (
            db.query(StockMovement).filter(StockMovement.reagent_id == reagent.json()["id"]).count()
            == 0
        )
        message = (
            db.query(DH36InboundMessage)
            .filter(DH36InboundMessage.id == response.json()["message_id"])
            .one()
        )
        assert message.status == "rejected"
        assert message.result_id is None

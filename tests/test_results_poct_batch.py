"""Tests de la route POCT générique /results/poct-batch (Flux 2)."""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models import AuditEvent, Result, Sample, StockMovement


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sample(client, admin, *, sex: str = "M") -> str:
    pid = client.post(
        "/api/v1/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"PB-{uuid.uuid4().hex[:8]}",
            "first_name": "Poct",
            "last_name": "Batch",
            "birth_date": "1990-03-03",
            "sex": sex,
        },
    ).json()["id"]
    barcode = f"PB-{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/v1/samples",
        headers=admin,
        json={"barcode": barcode, "patient_id": pid, "status": "Recu"},
    )
    return barcode


def _device(client, admin, *, serial: str, name: str = "Precis Expert") -> None:
    client.post(
        "/api/v1/equipments",
        headers=admin,
        json={"name": name, "serial_number": serial, "type": "POCT"},
    )


def test_registered_precix_profile_is_refused_until_qualified(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    with SessionLocal() as db:
        result_count = db.query(Result).count()
        stock_count = db.query(StockMovement).count()
        success_audit_count = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type.in_(
                    ["result.poct_batch.create", "result.precis_expert.create"]
                )
            )
            .count()
        )

    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "items": [
                {"code": "GLU", "value": 0.95},
                {"code": "CHOL", "value": 1.7},
                {"code": "UA", "value": 42.0},
                {"code": "LAC", "value": 1.2},
                {"code": "KET", "value": 0.2},
            ],
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "poct_equipment_not_qualified"
    assert serial not in r.text

    with SessionLocal() as db:
        assert db.query(Result).count() == result_count
        assert db.query(StockMovement).count() == stock_count
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type.in_(
                    ["result.poct_batch.create", "result.precis_expert.create"]
                )
            )
            .count()
            == success_audit_count
        )
        sample = db.query(Sample).filter(Sample.barcode == barcode).one()
        assert sample.status == "Recu"


def test_no_critical_threshold_is_applied_before_qualification(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "items": [{"code": "GLU", "value": 0.45}],
        },
    )
    assert r.status_code == 409, r.text


def test_non_precix_equipment_is_refused(client) -> None:
    admin = _auth(client)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial, name="Generic POCT")
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "device_model": "Generic POCT",
            "items": [{"code": "GLU", "value": 1.0, "unit": "synthetic-unit"}],
        },
    )
    assert r.status_code == 409, r.text


def test_unknown_analyte_code_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "items": [{"code": "HBA1C", "value": 6.0}],
        },
    )
    assert r.status_code == 422


def test_duplicate_analyte_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "items": [
                {"code": "GLU", "value": 0.9},
                {"code": "GLU", "value": 1.0},
            ],
        },
    )
    assert r.status_code == 422


def test_empty_batch_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={"sample_barcode": barcode, "device_serial": serial, "items": []},
    )
    assert r.status_code == 422


def test_missing_value_is_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)
    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": serial,
            "items": [{"code": "LAC", "unit": "synthetic-unit"}],
        },
    )
    assert r.status_code == 422


def test_unknown_device_rejected(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "device_serial": "PE-DOES-NOT-EXIST",
            "items": [{"code": "GLU", "value": 0.9}],
        },
    )
    assert r.status_code == 400


def test_unknown_barcode_returns_404(client) -> None:
    admin = _auth(client)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)
    r = client.post(
        "/api/v1/results/poct-batch",
        headers=admin,
        json={
            "sample_barcode": "NOPE-404",
            "device_serial": serial,
            "items": [{"code": "GLU", "value": 0.9}],
        },
    )
    assert r.status_code == 404


def test_legacy_precis_expert_route_is_also_fail_closed(client) -> None:
    admin = _auth(client)
    barcode = _sample(client, admin)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    r = client.post(
        "/api/v1/results/precis-expert",
        headers=admin,
        json={
            "sample_barcode": barcode,
            "equipment_serial": serial,
            "glucose_raw": 0.95,
            "cholesterol_raw": 1.7,
            "uric_acid_raw": 42.0,
            "lactate_raw": 1.2,
            "ketones_raw": 0.2,
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "poct_equipment_not_qualified"

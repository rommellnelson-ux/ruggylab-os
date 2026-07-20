"""Tests de la route POCT générique /results/poct-batch (Flux 2)."""

from __future__ import annotations

import uuid


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


def test_batch_of_five_analytes_persisted(client) -> None:
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
                {"code": "GLU", "value": 0.95},
                {"code": "CHOL", "value": 1.7},
                {"code": "UA", "value": 42.0},
                {"code": "LAC", "value": 1.2},
                {"code": "KET", "value": 0.2},
            ],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_critical"] is False
    assert len(body["analytes"]) == 5
    codes = {a["code"] for a in body["analytes"]}
    assert codes == {"GLU", "CHOL", "UA", "LAC", "KET"}
    # L'unité par défaut du catalogue est appliquée quand elle est omise.
    glu = next(a for a in body["analytes"] if a["code"] == "GLU")
    assert glu["point"]["unit"] == "g/L"
    assert glu["point"]["status"] == "N"


def test_critical_glucose_flags_result(client) -> None:
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
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_critical"] is True
    point = body["analytes"][0]["point"]
    assert point["status"] == "L"
    assert point["is_critical"] is True


def test_uric_acid_range_differs_by_sex(client) -> None:
    admin = _auth(client)
    serial = f"PE-{uuid.uuid4().hex[:6]}"
    _device(client, admin, serial=serial)

    def submit(sex: str) -> dict:
        barcode = _sample(client, admin, sex=sex)
        return client.post(
            "/api/v1/results/poct-batch",
            headers=admin,
            json={
                "sample_barcode": barcode,
                "device_serial": serial,
                "items": [{"code": "UA", "value": 65.0}],
            },
        ).json()["analytes"][0]["point"]

    # 65 mg/L : normal chez l'homme (35-72), élevé chez la femme (26-60).
    assert submit("M")["status"] == "N"
    assert submit("F")["status"] == "H"


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


def test_legacy_precis_expert_route_still_works(client) -> None:
    """La route historique doit rester intacte (rétrocompatibilité UI)."""
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
    assert r.status_code == 201, r.text
    assert r.json()["is_critical"] is False

"""Régressions RBAC — cloisonnement des échantillons par unité patient."""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models import Sample


def _admin(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _technician(client, admin: dict[str, str], *, unit: str) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    username = f"sample-rbac-{suffix}"
    response = client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "username": username,
            "password": "SyntheticPass123!",
            "role": "technician",
            "unit": unit,
        },
    )
    assert response.status_code == 201, response.text
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": "SyntheticPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _patient(client, admin: dict[str, str], *, unit: str | None) -> int:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "ipp_unique_id": f"SAMPLE-RBAC-{suffix}",
        "first_name": "Synthetic",
        "last_name": "Boundary",
        "birth_date": "1980-01-01",
        "sex": "F",
        "unit": unit,
    }
    response = client.post("/api/v1/patients", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _sample(
    client,
    admin: dict[str, str],
    *,
    patient_id: int,
    aspect: str = "conforme",
) -> dict:
    response = client.post(
        "/api/v1/samples",
        headers=admin,
        json={
            "barcode": f"SAMPLE-RBAC-{uuid.uuid4().hex[:10]}",
            "patient_id": patient_id,
            "status": "Recu",
            "aspect": aspect,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_unit_technician_lists_only_own_and_unassigned_samples(client) -> None:
    admin = _admin(client)
    own = _sample(client, admin, patient_id=_patient(client, admin, unit="hematologie"))
    other = _sample(client, admin, patient_id=_patient(client, admin, unit="biochimie"))
    shared = _sample(client, admin, patient_id=_patient(client, admin, unit=None))
    technician = _technician(client, admin, unit="hematologie")

    response = client.get("/api/v1/samples", headers=technician)

    assert response.status_code == 200, response.text
    visible = {sample["barcode"] for sample in response.json()}
    assert own["barcode"] in visible
    assert shared["barcode"] in visible
    assert other["barcode"] not in visible


def test_unit_technician_cannot_resolve_other_unit_barcode(client) -> None:
    admin = _admin(client)
    other = _sample(client, admin, patient_id=_patient(client, admin, unit="biochimie"))
    technician = _technician(client, admin, unit="hematologie")

    response = client.get(
        f"/api/v1/samples/by-barcode/{other['barcode']}",
        headers=technician,
    )

    assert response.status_code == 403


def test_unit_technician_cannot_create_sample_for_other_unit_patient(client) -> None:
    admin = _admin(client)
    other_patient_id = _patient(client, admin, unit="biochimie")
    technician = _technician(client, admin, unit="hematologie")
    barcode = f"SAMPLE-RBAC-DENIED-{uuid.uuid4().hex[:8]}"

    response = client.post(
        "/api/v1/samples",
        headers=technician,
        json={"barcode": barcode, "patient_id": other_patient_id, "status": "Recu"},
    )

    assert response.status_code == 403
    with SessionLocal() as verification:
        assert verification.query(Sample).filter(Sample.barcode == barcode).first() is None


def test_unit_technician_cannot_update_other_unit_sample(client) -> None:
    admin = _admin(client)
    other = _sample(client, admin, patient_id=_patient(client, admin, unit="biochimie"))
    technician = _technician(client, admin, unit="hematologie")

    response = client.patch(
        f"/api/v1/samples/{other['id']}",
        headers=technician,
        json={"status": "Termine"},
    )

    assert response.status_code == 403
    with SessionLocal() as verification:
        sample = verification.query(Sample).filter(Sample.id == other["id"]).one()
        assert sample.status == "Recu"


def test_unit_technician_quality_summary_excludes_other_unit(client) -> None:
    admin = _admin(client)
    _sample(
        client,
        admin,
        patient_id=_patient(client, admin, unit="hematologie"),
        aspect="hemolyse",
    )
    _sample(
        client,
        admin,
        patient_id=_patient(client, admin, unit="biochimie"),
        aspect="lipemique",
    )
    technician = _technician(client, admin, unit="hematologie")

    response = client.get("/api/v1/samples/quality-summary", headers=technician)

    assert response.status_code == 200, response.text
    assert response.json()["by_aspect"] == {"hemolyse": 1}


def test_unit_technician_cannot_create_patient_for_other_unit(client) -> None:
    admin = _admin(client)
    technician = _technician(client, admin, unit="hematologie")

    response = client.post(
        "/api/v1/patients",
        headers=technician,
        json={
            "ipp_unique_id": f"SAMPLE-RBAC-DENIED-{uuid.uuid4().hex[:8]}",
            "first_name": "Synthetic",
            "last_name": "CrossUnit",
            "birth_date": "1980-01-01",
            "sex": "F",
            "unit": "biochimie",
        },
    )

    assert response.status_code == 403

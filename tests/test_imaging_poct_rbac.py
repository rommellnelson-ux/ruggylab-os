"""Tests — cloisonnement RBAC par unité de imaging et results-poct (F4).

Un technicien rattaché à une unité ne peut pas agir sur les échantillons /
résultats / jobs d'imagerie d'une autre unité.
"""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _tech(client, admin, *, unit: str) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"t_{u}", "password": "TechPass123!", "role": "technician", "unit": unit},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"t_{u}", "password": "TechPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _sample(client, admin, *, unit: str) -> str:
    pid = client.post(
        "/api/v1/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"IM-{uuid.uuid4().hex[:8]}",
            "first_name": "Im",
            "last_name": "Test",
            "birth_date": "1980-01-01",
            "sex": "M",
            "unit": unit,
        },
    ).json()["id"]
    barcode = f"IM-{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/v1/samples",
        headers=admin,
        json={"barcode": barcode, "patient_id": pid, "status": "Recu"},
    )
    return barcode


def _poct_payload(barcode: str) -> dict:
    return {
        "sample_barcode": barcode,
        "equipment_serial": "PE-TEST-1",
        "glucose_raw": 1.0,
        "cholesterol_raw": 1.5,
        "uric_acid_raw": 40.0,
        "lactate_raw": 1.0,
        "ketones_raw": 0.1,
    }


class TestImagingScope:
    def test_capture_denied_other_unit(self, client):
        admin = _auth(client)
        barcode = _sample(client, admin, unit="biochimie")
        tech = _tech(client, admin, unit="hematologie")
        r = client.post(
            "/api/v1/imaging/capture-microscope",
            headers=tech,
            json={"sample_barcode": barcode},
        )
        assert r.status_code == 403

    def test_capture_allowed_same_unit(self, client):
        admin = _auth(client)
        barcode = _sample(client, admin, unit="hematologie")
        tech = _tech(client, admin, unit="hematologie")
        r = client.post(
            "/api/v1/imaging/capture-microscope",
            headers=tech,
            json={"sample_barcode": barcode},
        )
        assert r.status_code == 201, r.text

    def test_malaria_job_denied_other_unit(self, client):
        admin = _auth(client)
        barcode = _sample(client, admin, unit="biochimie")
        rid = client.post(
            "/api/v1/imaging/capture-microscope", headers=admin, json={"sample_barcode": barcode}
        ).json()["result_id"]
        job = client.post(f"/api/v1/imaging/malaria/analyze/{rid}", headers=admin)
        assert job.status_code in (200, 202), job.text
        job_id = job.json()["id"]
        tech = _tech(client, admin, unit="hematologie")
        assert (
            client.get(f"/api/v1/imaging/malaria/jobs/{job_id}", headers=tech).status_code == 403
        )
        assert (
            client.get(f"/api/v1/imaging/malaria/jobs/{job_id}", headers=admin).status_code == 200
        )


class TestPoctScope:
    def test_poct_denied_other_unit(self, client):
        admin = _auth(client)
        barcode = _sample(client, admin, unit="biochimie")
        tech = _tech(client, admin, unit="hematologie")
        r = client.post(
            "/api/v1/results/precis-expert", headers=tech, json=_poct_payload(barcode)
        )
        assert r.status_code == 403

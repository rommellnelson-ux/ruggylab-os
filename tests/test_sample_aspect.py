"""Tests — aspect / qualité pré-analytique de l'échantillon + interférences."""

from __future__ import annotations

import uuid

from app.services.preanalytic import interference_warning, interfering_analytes


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _patient(client, admin) -> int:
    return client.post(
        "/api/v1/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"AS-{uuid.uuid4().hex[:8]}",
            "first_name": "As",
            "last_name": "Pect",
            "birth_date": "1980-01-01",
            "sex": "M",
        },
    ).json()["id"]


class TestSampleAspectApi:
    def test_create_with_aspect(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)
        r = client.post(
            "/api/v1/samples",
            headers=admin,
            json={"barcode": f"AS-{uuid.uuid4().hex[:8]}", "patient_id": pid, "aspect": "hemolyse"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["aspect"] == "hemolyse"

    def test_invalid_aspect_rejected(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)
        r = client.post(
            "/api/v1/samples",
            headers=admin,
            json={"barcode": f"AS-{uuid.uuid4().hex[:8]}", "patient_id": pid, "aspect": "rouge"},
        )
        assert r.status_code == 422

    def test_update_aspect(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)
        sid = client.post(
            "/api/v1/samples",
            headers=admin,
            json={"barcode": f"AS-{uuid.uuid4().hex[:8]}", "patient_id": pid},
        ).json()["id"]
        r = client.patch(f"/api/v1/samples/{sid}", headers=admin, json={"aspect": "lipemique"})
        assert r.status_code == 200
        assert r.json()["aspect"] == "lipemique"

    def test_quality_summary(self, client):
        admin = _auth(client)
        pid = _patient(client, admin)
        client.post(
            "/api/v1/samples",
            headers=admin,
            json={"barcode": f"AS-{uuid.uuid4().hex[:8]}", "patient_id": pid, "aspect": "hemolyse"},
        )
        s = client.get("/api/v1/samples/quality-summary", headers=admin)
        assert s.status_code == 200, s.text
        body = s.json()
        assert body["by_aspect"].get("hemolyse", 0) >= 1
        assert body["hemolysis_rate_pct"] > 0


class TestInterferenceLogic:
    def test_hemolysis_flags_potassium(self):
        assert interfering_analytes("hemolyse", {"K": 5.0, "WBC": 7}) == ["K"]
        assert interference_warning("hemolyse", {"K": 5.0}) is not None

    def test_conforme_no_warning(self):
        assert interfering_analytes("conforme", {"K": 5.0}) == []
        assert interference_warning("conforme", {"K": 5.0}) is None

    def test_unrelated_analyte_no_warning(self):
        assert interference_warning("hemolyse", {"WBC": 7.0}) is None

"""Tests — Dossier patient complet (history + FHIR bundle)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _make_patient(client, hdrs) -> int:
    return client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"PH-{_uid()}",
            "first_name": "Hist",
            "last_name": "Patient",
            "birth_date": "1975-07-20",
            "sex": "F",
        },
    ).json()["id"]


def _make_sample(client, hdrs, patient_id) -> int:
    return client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"PH-{_uid()}", "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


def _post_result(client, hdrs, sample_id, data_points) -> dict:
    r = client.post(
        "/api/v1/results",
        headers=hdrs,
        json={"sample_id": sample_id, "data_points": data_points, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestPatientHistory:
    def test_history_empty_patient(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        r = client.get(f"/api/v1/patients/{pid}/history", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["patient"]["id"] == pid
        assert data["result_count"] == 0
        assert data["sample_count"] == 0
        assert data["timeline"] == []
        assert data["trends"] == {}

    def test_history_with_results_builds_trends(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        s1 = _make_sample(client, hdrs, pid)
        s2 = _make_sample(client, hdrs, pid)
        _post_result(client, hdrs, s1, {"HGB": 120.0, "WBC": 5.0})
        _post_result(client, hdrs, s2, {"HGB": 130.0, "WBC": 6.0})
        r = client.get(f"/api/v1/patients/{pid}/history", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["result_count"] == 2
        assert data["sample_count"] == 2
        assert len(data["timeline"]) == 2
        # Trends per analyte
        assert "HGB" in data["trends"]
        assert "WBC" in data["trends"]
        hgb_series = [pt["value"] for pt in data["trends"]["HGB"]]
        assert hgb_series == [120.0, 130.0]  # chronological order

    def test_history_handles_dict_valued_datapoints(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        s1 = _make_sample(client, hdrs, pid)
        _post_result(client, hdrs, s1, {"PLT": {"value": 250.0, "status": "N"}})
        r = client.get(f"/api/v1/patients/{pid}/history", headers=hdrs)
        assert r.status_code == 200
        trends = r.json()["trends"]
        assert "PLT" in trends
        assert trends["PLT"][0]["value"] == 250.0

    def test_history_404(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/patients/999999/history", headers=hdrs)
        assert r.status_code == 404


class TestPatientFhirBundle:
    def test_fhir_bundle_structure(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        s1 = _make_sample(client, hdrs, pid)
        _post_result(client, hdrs, s1, {"HGB": 125.0})
        r = client.get(f"/api/v1/patients/{pid}/fhir-bundle", headers=hdrs)
        assert r.status_code == 200
        bundle = r.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "collection"
        assert bundle["total"] == 1
        assert len(bundle["entry"]) == 1
        assert bundle["entry"][0]["resource"]["resourceType"] == "DiagnosticReport"

    def test_fhir_bundle_empty_patient(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        r = client.get(f"/api/v1/patients/{pid}/fhir-bundle", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_fhir_bundle_404(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/patients/999999/fhir-bundle", headers=hdrs)
        assert r.status_code == 404

    def test_search_by_rank(self, client):
        """La recherche patient couvre aussi le grade (rank)."""
        hdrs = _auth(client)
        rank = f"Capitaine-{_uid()[:5]}"
        client.post(
            "/api/v1/patients",
            headers=hdrs,
            json={
                "ipp_unique_id": f"PH-{_uid()}",
                "first_name": "Rank",
                "last_name": "Search",
                "birth_date": "1970-01-01",
                "sex": "M",
                "rank": rank,
            },
        )
        r = client.get(f"/api/v1/patients?q={rank}", headers=hdrs)
        assert r.status_code == 200
        assert any(p.get("rank") == rank for p in r.json()["items"])

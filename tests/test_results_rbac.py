"""Tests — cloisonnement RBAC par unité sur les endpoints /results/* et auth facilities."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_tech(client, admin, *, unit: str | None) -> dict[str, str]:
    u = _uid()
    body = {"username": f"t_{u}", "password": "TechPass123!", "role": "technician"}
    if unit is not None:
        body["unit"] = unit
    client.post("/api/v1/users", headers=admin, json=body)
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"t_{u}", "password": "TechPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_result(client, admin, *, unit: str | None, critical=False) -> int:
    body = {
        "ipp_unique_id": f"RB-{_uid()}",
        "first_name": "Rb",
        "last_name": "Test",
        "birth_date": "1980-01-01",
        "sex": "M",
    }
    if unit is not None:
        body["unit"] = unit
    pid = client.post("/api/v1/patients", headers=admin, json=body).json()["id"]
    sid = client.post(
        "/api/v1/samples",
        headers=admin,
        json={"barcode": f"RB-{_uid()}", "patient_id": pid, "status": "Recu"},
    ).json()["id"]
    data = {"WBC": 99.0} if critical else {"WBC": 5.0}
    # seuil critique WBC pour générer un critique si demandé
    if critical:
        client.post(
            "/api/v1/critical-ranges",
            headers=admin,
            json={"analyte": "WBC", "low_critical": None, "high_critical": 1.0, "unit": "u"},
        )
    r = client.post(
        "/api/v1/results",
        headers=admin,
        json={"sample_id": sid, "data_points": data, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestResultsUnitScope:
    def test_cockpit_excludes_other_unit(self, client):
        admin = _auth(client)
        rid_bio = _make_result(client, admin, unit="biochimie")
        rid_hema = _make_result(client, admin, unit="hematologie")
        tech_hema = _make_tech(client, admin, unit="hematologie")
        ids = {
            item["result"]["id"]
            for item in client.get("/api/v1/results/cockpit", headers=tech_hema).json()
        }
        assert rid_hema in ids
        assert rid_bio not in ids

    def test_detail_denied_other_unit(self, client):
        admin = _auth(client)
        rid_bio = _make_result(client, admin, unit="biochimie")
        tech_hema = _make_tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/results/{rid_bio}/detail", headers=tech_hema).status_code == 403
        assert client.get(f"/api/v1/results/{rid_bio}", headers=tech_hema).status_code == 403
        assert (
            client.get(f"/api/v1/results/{rid_bio}/history", headers=tech_hema).status_code == 403
        )
        assert client.get(f"/api/v1/results/{rid_bio}/fhir", headers=tech_hema).status_code == 403
        assert (
            client.get(f"/api/v1/reports/results/{rid_bio}/pdf", headers=tech_hema).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/v1/reports/results/{rid_bio}/signature", headers=tech_hema
            ).status_code
            == 403
        )

    def test_detail_allowed_same_unit(self, client):
        admin = _auth(client)
        rid = _make_result(client, admin, unit="hematologie")
        tech_hema = _make_tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/results/{rid}/detail", headers=tech_hema).status_code == 200

    def test_unaffected_patient_visible(self, client):
        admin = _auth(client)
        rid = _make_result(client, admin, unit=None)  # patient sans unité = pool partagé
        tech_hema = _make_tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/results/{rid}", headers=tech_hema).status_code == 200

    def test_admin_sees_all(self, client):
        admin = _auth(client)
        rid_bio = _make_result(client, admin, unit="biochimie")
        assert client.get(f"/api/v1/results/{rid_bio}/detail", headers=admin).status_code == 200

    def test_technician_cannot_finalize_biological_validation(self, client):
        admin = _auth(client)
        rid = _make_result(client, admin, unit="hematologie")
        tech_hema = _make_tech(client, admin, unit="hematologie")
        assert client.post(f"/api/v1/results/{rid}/validate", headers=tech_hema).status_code == 403
        assert client.get("/api/v1/results/review-queue", headers=tech_hema).status_code == 403

    def test_admin_can_review_pending_results_in_batch(self, client):
        admin = _auth(client)
        first = _make_result(client, admin, unit="hematologie")
        second = _make_result(client, admin, unit="biochimie")

        queue = client.get("/api/v1/results/review-queue", headers=admin)
        assert queue.status_code == 200
        queued_ids = {item["result"]["id"] for item in queue.json()["items"]}
        assert {first, second} <= queued_ids

        reviewed = client.post(
            "/api/v1/results/review-batch",
            headers=admin,
            json={"result_ids": [first, second, first, 999999]},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["reviewed"] == [first, second]
        assert reviewed.json()["skipped"]["999999"] == "introuvable"

        remaining = client.get("/api/v1/results/review-queue", headers=admin).json()
        remaining_ids = {item["result"]["id"] for item in remaining["items"]}
        assert first not in remaining_ids
        assert second not in remaining_ids

    def test_unhandled_critical_value_blocks_direct_pdf(self, client):
        admin = _auth(client)
        rid = _make_result(client, admin, unit="hematologie", critical=True)
        assert client.get(f"/api/v1/reports/results/{rid}/pdf", headers=admin).status_code == 409
        assert client.patch(f"/api/v1/results/{rid}/ack-critical", headers=admin).status_code == 200
        assert client.get(f"/api/v1/reports/results/{rid}/pdf", headers=admin).status_code == 200

    def test_ack_batch_skips_out_of_scope(self, client):
        admin = _auth(client)
        rid_bio = _make_result(client, admin, unit="biochimie", critical=True)
        tech_hema = _make_tech(client, admin, unit="hematologie")
        r = client.patch(
            "/api/v1/results/ack-critical-batch",
            headers=tech_hema,
            json={"result_ids": [rid_bio]},
        )
        assert r.status_code == 200
        body = r.json()
        assert rid_bio not in body["acknowledged"]
        assert body["skipped"].get(str(rid_bio)) == "hors périmètre"


class TestMilitaryFacilitiesAuth:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/military-facilities").status_code == 401

    def test_ok_with_auth(self, client):
        hdrs = _auth(client)
        assert client.get("/api/v1/military-facilities", headers=hdrs).status_code == 200

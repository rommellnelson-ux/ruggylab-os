"""Tests — Module qualité : non-conformités (NC) + actions correctives (CAPA)."""

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


def _tech(client) -> dict[str, str] | None:
    hdrs = _auth(client)
    u = _uid()
    client.post(
        "/api/v1/users",
        headers=hdrs,
        json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
    )
    tok = (
        client.post(
            "/api/v1/login/access-token",
            data={"username": f"tech_{u}", "password": "TechPass123!"},
        )
        .json()
        .get("access_token")
    )
    return {"Authorization": f"Bearer {tok}"} if tok else None


def _create_nc(client, hdrs, **over) -> dict:
    body = {"title": f"NC test {_uid()}", "severity": "major", "source": "qc"}
    body.update(over)
    r = client.post("/api/v1/quality/non-conformities", headers=hdrs, json=body)
    assert r.status_code == 201, r.text
    return r.json()


class TestNonConformityCrud:
    def test_create_and_get(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        assert nc["status"] == "open"
        assert nc["detected_by_id"] is not None
        got = client.get(f"/api/v1/quality/non-conformities/{nc['id']}", headers=hdrs)
        assert got.status_code == 200
        assert got.json()["id"] == nc["id"]

    def test_technician_can_declare(self, client):
        tech = _tech(client)
        if tech:
            nc = _create_nc(client, tech)
            assert nc["status"] == "open"

    def test_list_filter_by_status(self, client):
        hdrs = _auth(client)
        _create_nc(client, hdrs)
        r = client.get("/api/v1/quality/non-conformities?status=open", headers=hdrs)
        assert r.status_code == 200
        assert all(nc["status"] == "open" for nc in r.json())

    def test_create_is_audited(self, client):
        hdrs = _auth(client)
        _create_nc(client, hdrs)
        r = client.get("/api/v1/audit-events?event_type=quality.nc.create", headers=hdrs)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1


class TestNonConformityWorkflow:
    def test_valid_transition_sequence(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        nid = nc["id"]
        for target in ("analysis", "action", "verification", "closed"):
            r = client.post(
                f"/api/v1/quality/non-conformities/{nid}/transition",
                headers=hdrs,
                json={"status": target},
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == target
        # Fermée → closed_at renseigné
        assert client.get(f"/api/v1/quality/non-conformities/{nid}", headers=hdrs).json()[
            "closed_at"
        ]

    def test_invalid_transition_rejected(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        # open → verification (saut interdit)
        r = client.post(
            f"/api/v1/quality/non-conformities/{nc['id']}/transition",
            headers=hdrs,
            json={"status": "verification"},
        )
        assert r.status_code == 409

    def test_transition_requires_officer(self, client):
        admin = _auth(client)
        nc = _create_nc(client, admin)
        tech = _tech(client)
        if tech:
            r = client.post(
                f"/api/v1/quality/non-conformities/{nc['id']}/transition",
                headers=tech,
                json={"status": "analysis"},
            )
            assert r.status_code == 403

    def test_transition_is_audited(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        client.post(
            f"/api/v1/quality/non-conformities/{nc['id']}/transition",
            headers=hdrs,
            json={"status": "analysis", "root_cause": "Cause racine identifiée"},
        )
        r = client.get("/api/v1/audit-events?event_type=quality.nc.transition", headers=hdrs)
        assert len(r.json()["items"]) >= 1


class TestCorrectiveActions:
    def test_add_and_update_action(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        r = client.post(
            f"/api/v1/quality/non-conformities/{nc['id']}/actions",
            headers=hdrs,
            json={"action_type": "corrective", "description": "Recalibrer l'automate"},
        )
        assert r.status_code == 201, r.text
        action_id = r.json()["id"]
        # Mise à jour du statut → done renseigne completed_at
        upd = client.patch(
            f"/api/v1/quality/actions/{action_id}",
            headers=hdrs,
            json={"status": "done", "effectiveness_checked": True},
        )
        assert upd.status_code == 200
        assert upd.json()["status"] == "done"
        assert upd.json()["completed_at"] is not None
        assert upd.json()["effectiveness_checked"] is True

    def test_action_appears_in_nc(self, client):
        hdrs = _auth(client)
        nc = _create_nc(client, hdrs)
        client.post(
            f"/api/v1/quality/non-conformities/{nc['id']}/actions",
            headers=hdrs,
            json={"description": "Action liée"},
        )
        got = client.get(f"/api/v1/quality/non-conformities/{nc['id']}", headers=hdrs)
        assert len(got.json()["actions"]) == 1


class TestQualityDashboard:
    def test_dashboard_counts(self, client):
        hdrs = _auth(client)
        _create_nc(client, hdrs, severity="critical")
        r = client.get("/api/v1/quality/dashboard", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["open_count"] >= 1
        assert data["by_severity"]["critical"] >= 1
        assert "by_status" in data

"""Tests — Registre des Accidents d'Exposition au Sang (AES)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user(client, admin, role: str) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"{role}_{u}", "password": "RolePass123!", "role": role},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"{role}_{u}", "password": "RolePass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _declare(client, headers) -> dict:
    return client.post(
        "/api/v1/aes",
        headers=headers,
        json={
            "occurred_at": "2026-06-23T08:30:00",
            "exposure_type": "piqure",
            "location": "Paillasse hématologie",
            "circumstances": "Recapuchonnage d'aiguille",
            "immediate_measures": "Lavage + antiseptique",
        },
    )


class TestAesRegister:
    def test_any_agent_can_declare(self, client):
        admin = _auth(client)
        tech = _user(client, admin, "technician")
        r = _declare(client, tech)
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "declared"

    def test_invalid_exposure_type_rejected(self, client):
        admin = _auth(client)
        r = client.post(
            "/api/v1/aes",
            headers=admin,
            json={"occurred_at": "2026-06-23T08:30:00", "exposure_type": "xxx", "circumstances": "x"},
        )
        assert r.status_code == 422

    def test_listing_reserved_to_management(self, client):
        admin = _auth(client)
        tech = _user(client, admin, "technician")
        _declare(client, tech)
        assert client.get("/api/v1/aes", headers=tech).status_code == 403
        rows = client.get("/api/v1/aes", headers=admin)
        assert rows.status_code == 200
        assert len(rows.json()) >= 1

    def test_followup_and_closure(self, client):
        admin = _auth(client)
        officer = _user(client, admin, "officer")
        aes_id = _declare(client, admin).json()["id"]
        r = client.patch(
            f"/api/v1/aes/{aes_id}",
            headers=officer,
            json={"status": "closed", "source_serology": "VIH négatif", "followup_notes": "Suivi 6 mois RAS"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "closed"
        assert body["closed_at"] is not None
        assert body["source_serology"] == "VIH négatif"

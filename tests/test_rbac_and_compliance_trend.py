"""Tests — RBAC dossiers patient (scoping unité) + tendance de conformité + bus."""
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


def _make_user(client, admin, *, unit: str | None, role: str = "technician") -> dict[str, str]:
    u = _uid()
    body = {"username": f"u_{u}", "password": "UserPass123!", "role": role}
    if unit is not None:
        body["unit"] = unit
    client.post("/api/v1/users", headers=admin, json=body)
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"u_{u}", "password": "UserPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_patient(client, hdrs, *, unit: str | None) -> int:
    body = {
        "ipp_unique_id": f"RB-{_uid()}",
        "first_name": "Rb",
        "last_name": "Test",
        "birth_date": "1980-01-01",
        "sex": "M",
    }
    if unit is not None:
        body["unit"] = unit
    return client.post("/api/v1/patients", headers=hdrs, json=body).json()["id"]


class TestPatientRbacScoping:
    def test_technician_sees_only_own_unit(self, client):
        admin = _auth(client)
        p_hema = _make_patient(client, admin, unit="hematologie")
        p_bio = _make_patient(client, admin, unit="biochimie")
        p_pool = _make_patient(client, admin, unit=None)

        tech_hema = _make_user(client, admin, unit="hematologie")
        # Liste : voit son unité + pool, pas l'autre unité
        ids = {p["id"] for p in client.get("/api/v1/patients?limit=100", headers=tech_hema).json()["items"]}
        assert p_hema in ids
        assert p_pool in ids
        assert p_bio not in ids

    def test_technician_denied_other_unit_detail(self, client):
        admin = _auth(client)
        p_bio = _make_patient(client, admin, unit="biochimie")
        tech_hema = _make_user(client, admin, unit="hematologie")
        r = client.get(f"/api/v1/patients/{p_bio}", headers=tech_hema)
        assert r.status_code == 403

    def test_denied_access_is_audited(self, client):
        admin = _auth(client)
        p_bio = _make_patient(client, admin, unit="biochimie")
        tech_hema = _make_user(client, admin, unit="hematologie")
        client.get(f"/api/v1/patients/{p_bio}/history", headers=tech_hema)
        r = client.get("/api/v1/audit-events?event_type=patient.access.denied", headers=admin)
        assert r.status_code == 200
        assert any(e["entity_id"] == str(p_bio) for e in r.json()["items"])

    def test_admin_sees_all_units(self, client):
        admin = _auth(client)
        p_bio = _make_patient(client, admin, unit="biochimie")
        r = client.get(f"/api/v1/patients/{p_bio}", headers=admin)
        assert r.status_code == 200

    def test_transversal_technician_sees_all(self, client):
        admin = _auth(client)
        p_bio = _make_patient(client, admin, unit="biochimie")
        tech_transversal = _make_user(client, admin, unit=None)  # unité NULL = transversal
        r = client.get(f"/api/v1/patients/{p_bio}", headers=tech_transversal)
        assert r.status_code == 200


class TestComplianceTrend:
    def test_trend_structure(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/reports/compliance-trend?months=6", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["months"] == 6
        assert len(data["series"]) == 6
        assert "has_drift" in data
        for entry in data["series"]:
            assert "month" in entry
            assert "validation_rate_pct" in entry
            assert "drift" in entry

    def test_compliance_html_report(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/reports/compliance-report?days=30", headers=hdrs)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "Rapport de conformité" in r.text


class TestNotificationBus:
    def test_publish_reaches_subscriber(self):
        import asyncio

        from app.services.notification_bus import NotificationBus

        async def scenario() -> dict:
            local_bus = NotificationBus()
            q = local_bus.subscribe()
            local_bus.publish({"type": "critical", "result_id": 7})
            return await asyncio.wait_for(q.get(), timeout=1)

        event = asyncio.run(scenario())
        assert event["type"] == "critical"
        assert event["result_id"] == 7

    def test_unsubscribe_removes_queue(self):
        from app.services.notification_bus import NotificationBus

        b = NotificationBus()
        q = b.subscribe()
        assert b.subscriber_count == 1
        b.unsubscribe(q)
        assert b.subscriber_count == 0

    def test_publish_alert_event_never_raises(self):
        from app.services.notification_bus import publish_alert_event

        # Ne doit jamais lever, même sans abonné / hors boucle asyncio
        publish_alert_event("critical", result_id=1)

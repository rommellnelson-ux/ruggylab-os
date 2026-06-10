"""Tests — Fan-out Redis du bus de notifications + édition patient (PATCH)."""
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


def _make_patient(client, hdrs, **over) -> dict:
    body = {
        "ipp_unique_id": f"PU-{_uid()}",
        "first_name": "Up",
        "last_name": "Date",
        "birth_date": "1980-01-01",
        "sex": "M",
    }
    body.update(over)
    r = client.post("/api/v1/patients", headers=hdrs, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── Fan-out Redis (seam testé sans Redis réel) ──────────────────────────────

class TestRedisFanoutSeam:
    def test_publisher_receives_tagged_event(self):
        from app.services import notification_bus as nb

        received: list[dict] = []
        nb.set_redis_publisher(received.append)
        try:
            nb.publish_alert_event("critical", result_id=42)
        finally:
            nb.set_redis_publisher(None)
        assert len(received) == 1
        assert received[0]["type"] == "critical"
        assert received[0]["result_id"] == 42
        assert received[0]["_origin"] == nb.WORKER_ID

    def test_local_bus_still_receives_when_redis_active(self):
        import asyncio

        from app.services import notification_bus as nb

        async def scenario() -> dict:
            q = nb.bus.subscribe()
            nb.set_redis_publisher(lambda e: None)
            try:
                nb.publish_alert_event("delta", result_id=9)
                return await asyncio.wait_for(q.get(), timeout=1)
            finally:
                nb.set_redis_publisher(None)
                nb.bus.unsubscribe(q)

        event = asyncio.run(scenario())
        assert event["type"] == "delta"
        assert event["result_id"] == 9

    def test_inject_remote_event_skips_own_origin(self):
        import asyncio

        from app.services import notification_bus as nb

        async def scenario() -> bool:
            q = nb.bus.subscribe()
            try:
                # Message émis par CE worker → ignoré
                nb.inject_remote_event({"type": "critical", "_origin": nb.WORKER_ID})
                # Message d'un AUTRE worker → injecté
                nb.inject_remote_event({"type": "critical", "_origin": "other-worker", "result_id": 5})
                event = await asyncio.wait_for(q.get(), timeout=1)
                # Le premier (écho) a été ignoré ; on reçoit donc le second
                return event.get("result_id") == 5 and "_origin" not in event
            finally:
                nb.bus.unsubscribe(q)

        assert asyncio.run(scenario()) is True

    def test_publish_alert_event_no_publisher_is_safe(self):
        from app.services import notification_bus as nb

        nb.set_redis_publisher(None)
        # Ne doit pas lever
        nb.publish_alert_event("critical", result_id=1)


# ── Édition patient (PATCH) ─────────────────────────────────────────────────

class TestPatientUpdate:
    def test_update_unit(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs, unit="hematologie")
        r = client.patch(f"/api/v1/patients/{p['id']}", headers=hdrs, json={"unit": "biochimie"})
        assert r.status_code == 200, r.text
        assert r.json()["unit"] == "biochimie"

    def test_clear_unit_with_null(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs, unit="hematologie")
        r = client.patch(f"/api/v1/patients/{p['id']}", headers=hdrs, json={"unit": None})
        assert r.status_code == 200
        assert r.json()["unit"] is None

    def test_update_demographics(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs)
        r = client.patch(
            f"/api/v1/patients/{p['id']}",
            headers=hdrs,
            json={"rank": "Commandant", "last_name": "Nouveau"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rank"] == "Commandant"
        assert body["last_name"] == "Nouveau"
        # Champs non fournis inchangés
        assert body["first_name"] == "Up"

    def test_update_is_audited(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs)
        client.patch(f"/api/v1/patients/{p['id']}", headers=hdrs, json={"unit": "x"})
        r = client.get("/api/v1/audit-events?event_type=patient.update", headers=hdrs)
        assert any(e["entity_id"] == str(p["id"]) for e in r.json()["items"])

    def test_empty_update_rejected(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs)
        r = client.patch(f"/api/v1/patients/{p['id']}", headers=hdrs, json={})
        assert r.status_code == 400

    def test_future_birth_date_rejected(self, client):
        hdrs = _auth(client)
        p = _make_patient(client, hdrs)
        r = client.patch(
            f"/api/v1/patients/{p['id']}", headers=hdrs, json={"birth_date": "2099-01-01"}
        )
        assert r.status_code == 422

    def test_update_requires_officer(self, client):
        admin = _auth(client)
        p = _make_patient(client, admin)
        u = _uid()
        client.post(
            "/api/v1/users",
            headers=admin,
            json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
        )
        tok = client.post(
            "/api/v1/login/access-token",
            data={"username": f"tech_{u}", "password": "TechPass123!"},
        ).json().get("access_token")
        if tok:
            r = client.patch(
                f"/api/v1/patients/{p['id']}",
                headers={"Authorization": f"Bearer {tok}"},
                json={"unit": "x"},
            )
            assert r.status_code == 403

    def test_update_nonexistent(self, client):
        hdrs = _auth(client)
        r = client.patch("/api/v1/patients/999999", headers=hdrs, json={"unit": "x"})
        assert r.status_code == 404

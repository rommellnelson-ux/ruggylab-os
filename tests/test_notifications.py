"""Tests — Notifications temps-réel (feed REST + WebSocket)."""

from __future__ import annotations

import uuid

import pytest
from starlette.websockets import WebSocketDisconnect


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _token(client) -> str:
    return client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _make_critical_result(client, hdrs) -> int:
    """Crée un résultat critique non-acquitté via un seuil critique."""
    client.post(
        "/api/v1/critical-ranges",
        headers=hdrs,
        json={"analyte": "WBC", "low_critical": None, "high_critical": 1.0, "unit": "unit"},
    )
    pid = client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"NT-{_uid()}",
            "first_name": "Notif",
            "last_name": "Test",
            "birth_date": "1990-01-01",
            "sex": "M",
        },
    ).json()["id"]
    sid = client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"NT-{_uid()}", "patient_id": pid, "status": "Recu"},
    ).json()["id"]
    r = client.post(
        "/api/v1/results",
        headers=hdrs,
        json={"sample_id": sid, "data_points": {"WBC": 99.0}, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    assert r.json()["is_critical"] is True
    return r.json()["id"]


class TestNotificationsFeed:
    def test_feed_structure(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/notifications/feed", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        for field in (
            "generated_at",
            "total",
            "counts",
            "criticals",
            "deltas",
            "expiring",
            "qc_rejects",
        ):
            assert field in data, f"Champ manquant: {field}"
        for c in ("criticals", "deltas", "expiring", "qc_rejects"):
            assert c in data["counts"]

    def test_feed_reflects_critical(self, client):
        hdrs = _auth(client)
        _make_critical_result(client, hdrs)
        r = client.get("/api/v1/notifications/feed", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["counts"]["criticals"] >= 1
        assert data["total"] >= 1

    def test_feed_requires_auth(self, client):
        r = client.get("/api/v1/notifications/feed")
        assert r.status_code == 401


class TestNotificationsWebSocket:
    def test_ws_without_token_rejected(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/notifications/ws") as ws:
                ws.receive_json()

    def test_ws_with_invalid_token_rejected(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/notifications/ws?token=not-a-jwt") as ws:
                ws.receive_json()

    def test_ws_with_valid_token_receives_snapshot(self, client):
        tok = _token(client)
        with client.websocket_connect(f"/api/v1/notifications/ws?token={tok}") as ws:
            snap = ws.receive_json()
            assert "total" in snap
            assert "counts" in snap
            assert "criticals" in snap

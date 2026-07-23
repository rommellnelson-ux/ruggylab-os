"""Régressions RBAC sur alertes cliniques, rapports et suivi TAT."""

from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from typing import TypedDict, cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.services.notification_bus import publish_alert_event


class _Tokens(TypedDict):
    access_token: str
    refresh_token: str


class _SyntheticResult(TypedDict):
    id: int
    ipp: str
    barcode: str


def _login(client: TestClient, username: str, password: str) -> _Tokens:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return cast(_Tokens, response.json())


def _admin(client: TestClient) -> tuple[dict[str, str], _Tokens]:
    tokens = _login(client, "admin", "change_me_admin_password")
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


def _user(
    client: TestClient,
    admin: dict[str, str],
    *,
    role: str,
    unit: str | None = None,
) -> tuple[dict[str, str], _Tokens]:
    suffix = uuid.uuid4().hex[:8]
    username = f"clinical-rbac-{role}-{suffix}"
    password = "SyntheticPass123!"
    payload = {"username": username, "password": password, "role": role}
    if unit is not None:
        payload["unit"] = unit
    response = client.post("/api/v1/users", headers=admin, json=payload)
    assert response.status_code in (200, 201), response.text
    tokens = _login(client, username, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}, tokens


def _ensure_critical_range(client: TestClient, admin: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/critical-ranges",
        headers=admin,
        json={"analyte": "WBC", "low_critical": None, "high_critical": 1.0, "unit": "u"},
    )
    assert response.status_code in (201, 409), response.text


def _result(
    client: TestClient,
    admin: dict[str, str],
    *,
    unit: str | None,
    critical: bool = False,
    exam_code: str | None = None,
) -> _SyntheticResult:
    suffix = uuid.uuid4().hex[:8]
    ipp = f"CR-{suffix}"
    barcode = f"CR-S-{suffix}"
    patient_payload = {
        "ipp_unique_id": ipp,
        "first_name": "Synthetic",
        "last_name": suffix,
        "birth_date": "1980-01-01",
        "sex": "M",
    }
    if unit is not None:
        patient_payload["unit"] = unit
    patient_response = client.post("/api/v1/patients", headers=admin, json=patient_payload)
    assert patient_response.status_code == 201, patient_response.text
    sample_response = client.post(
        "/api/v1/samples",
        headers=admin,
        json={
            "barcode": barcode,
            "patient_id": patient_response.json()["id"],
            "status": "Recu",
        },
    )
    assert sample_response.status_code == 201, sample_response.text
    if critical:
        _ensure_critical_range(client, admin)
    result_payload = {
        "sample_id": sample_response.json()["id"],
        "data_points": {"WBC": 99.0 if critical else 0.5},
        "is_critical": False,
    }
    if exam_code is not None:
        result_payload["exam_code"] = exam_code
    result_response = client.post("/api/v1/results", headers=admin, json=result_payload)
    assert result_response.status_code == 201, result_response.text
    if critical:
        assert result_response.json()["is_critical"] is True
    return {
        "id": result_response.json()["id"],
        "ipp": ipp,
        "barcode": barcode,
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/epidemiology-export.csv",
        "/api/v1/reports/critical-compliance",
        "/api/v1/notifications/feed",
        "/api/v1/tat/dashboard",
    ],
)
def test_accountant_cannot_read_clinical_reports_or_alerts(
    client: TestClient,
    path: str,
) -> None:
    admin, _ = _admin(client)
    accountant, _ = _user(client, admin, role="accountant")

    response = client.get(path, headers=accountant)

    assert response.status_code == 403


def test_accountant_cannot_open_clinical_notifications_websocket(client: TestClient) -> None:
    admin, _ = _admin(client)
    _, tokens = _user(client, admin, role="accountant")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/v1/notifications/ws?token={tokens['access_token']}"
        ) as websocket:
            websocket.receive_json()


def test_unit_technician_reports_exclude_other_unit_results(client: TestClient) -> None:
    admin, _ = _admin(client)
    own = _result(client, admin, unit="hematologie", critical=True)
    other = _result(client, admin, unit="biochimie", critical=True)
    technician, _ = _user(client, admin, role="technician", unit="hematologie")

    compliance = client.get(
        "/api/v1/reports/critical-compliance?days=30",
        headers=technician,
    )
    assert compliance.status_code == 200, compliance.text
    compliance_ids = {row["result_id"] for row in compliance.json()["rows"]}
    assert own["id"] in compliance_ids
    assert other["id"] not in compliance_ids

    summary = client.get(
        "/api/v1/reports/epidemiology-summary?days=30",
        headers=technician,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_results"] == 1

    export = client.get(
        "/api/v1/reports/epidemiology-export.csv?days=30",
        headers=technician,
    )
    assert export.status_code == 200, export.text
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert {row["result_id"] for row in rows} == {str(own["id"])}
    assert own["ipp"] in export.text
    assert other["ipp"] not in export.text
    assert other["barcode"] not in export.text


def test_unit_technician_alert_feeds_exclude_other_unit_results(client: TestClient) -> None:
    admin, _ = _admin(client)
    own = _result(client, admin, unit="hematologie", critical=True)
    other = _result(client, admin, unit="biochimie", critical=True)
    technician, _ = _user(client, admin, role="technician", unit="hematologie")

    feed = client.get("/api/v1/notifications/feed", headers=technician)
    assert feed.status_code == 200, feed.text
    feed_ids = {row["result_id"] for row in feed.json()["criticals"]}
    assert own["id"] in feed_ids
    assert other["id"] not in feed_ids

    pending = client.get("/api/v1/critical-alerts/pending", headers=technician)
    assert pending.status_code == 200, pending.text
    pending_ids = {row["result_id"] for row in pending.json()}
    assert own["id"] in pending_ids
    assert other["id"] not in pending_ids


def test_unit_technician_tat_access_and_dashboard_are_scoped(client: TestClient) -> None:
    admin, _ = _admin(client)
    exam_code = f"RBAC-{uuid.uuid4().hex[:6].upper()}"
    target = client.post(
        "/api/v1/tat/targets",
        headers=admin,
        json={"exam_code": exam_code, "label": "Synthetic TAT", "target_minutes": 5},
    )
    assert target.status_code == 201, target.text
    own = _result(client, admin, unit="hematologie", exam_code=exam_code)
    other = _result(client, admin, unit="biochimie", exam_code=exam_code)
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    timestamps = {
        "registered_at": (now - dt.timedelta(hours=2)).isoformat(),
        "bio_validated_at": now.isoformat(),
    }
    for result_id in (own["id"], other["id"]):
        response = client.patch(
            f"/api/v1/tat/results/{result_id}",
            headers=admin,
            json=timestamps,
        )
        assert response.status_code == 200, response.text

    technician, _ = _user(client, admin, role="technician", unit="hematologie")
    assert client.get(f"/api/v1/tat/results/{other['id']}", headers=technician).status_code == 403
    denied_update = client.patch(
        f"/api/v1/tat/results/{other['id']}",
        headers=technician,
        json={"registered_at": (now - dt.timedelta(hours=3)).isoformat()},
    )
    assert denied_update.status_code == 403

    dashboard = client.get("/api/v1/tat/dashboard?days=7", headers=technician)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["total_measured"] == 1

    alerts = client.get("/api/v1/tat/alerts?days=7", headers=technician)
    assert alerts.status_code == 200, alerts.text
    assert {row["result_id"] for row in alerts.json()} == {own["id"]}


def test_websocket_suppresses_other_unit_critical_event(client: TestClient) -> None:
    admin, _ = _admin(client)
    _, tokens = _user(client, admin, role="technician", unit="hematologie")

    with client.websocket_connect(
        f"/api/v1/notifications/ws?token={tokens['access_token']}"
    ) as websocket:
        websocket.receive_json()
        other = _result(client, admin, unit="biochimie", critical=True)
        received = websocket.receive_json()

        assert received.get("type") != "critical_value_alert"
        assert other["id"] not in {row["result_id"] for row in received.get("criticals", [])}


def test_open_websocket_closes_after_access_token_logout(client: TestClient) -> None:
    admin, _ = _admin(client)
    headers, tokens = _user(client, admin, role="technician", unit="hematologie")

    with client.websocket_connect(
        f"/api/v1/notifications/ws?token={tokens['access_token']}"
    ) as websocket:
        websocket.receive_json()
        logout = client.post(
            "/api/v1/login/logout",
            headers=headers,
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert logout.status_code == 204
        publish_alert_event("authorization_refresh")

        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

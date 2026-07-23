"""Traçabilité atomique des mises à jour NC/CAPA."""

from __future__ import annotations

import json
import uuid
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import quality as quality_endpoint
from app.db.session import SessionLocal
from app.models import AuditEvent, CorrectiveAction, NonConformity


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_nc(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/quality/non-conformities",
        headers=headers,
        json={
            "title": f"NC synthétique {uuid.uuid4().hex[:10]}",
            "description": "Donnée synthétique sans patient.",
            "severity": "major",
            "source": "manual",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _create_action(client: TestClient, headers: dict[str, str], nc_id: int) -> int:
    response = client.post(
        f"/api/v1/quality/non-conformities/{nc_id}/actions",
        headers=headers,
        json={
            "action_type": "corrective",
            "description": "Action synthétique de vérification.",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _fail_capa_update(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("synthetic quality audit failure")


def test_capa_update_is_audited_without_notes_content(client: TestClient) -> None:
    headers = _auth(client)
    nc_id = _create_nc(client, headers)
    action_id = _create_action(client, headers, nc_id)
    notes = f"Note synthétique {uuid.uuid4().hex}"

    response = client.patch(
        f"/api/v1/quality/actions/{action_id}",
        headers=headers,
        json={
            "status": "done",
            "effectiveness_checked": True,
            "effectiveness_notes": notes,
        },
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "quality.capa.update",
                AuditEvent.entity_id == str(action_id),
            )
            .one_or_none()
        )
        assert event is not None
        payload = json.loads(event.payload or "{}")
        assert payload == {
            "fields": ["effectiveness_checked", "effectiveness_notes", "status"],
            "old_status": "planned",
            "new_status": "done",
            "old_effectiveness_checked": False,
            "new_effectiveness_checked": True,
        }
        assert notes not in (event.payload or "")


def test_capa_update_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    nc_id = _create_nc(client, headers)
    action_id = _create_action(client, headers, nc_id)
    monkeypatch.setattr(quality_endpoint, "log_audit_event", _fail_capa_update)

    with pytest.raises(RuntimeError, match="synthetic quality audit failure"):
        client.patch(
            f"/api/v1/quality/actions/{action_id}",
            headers=headers,
            json={
                "status": "done",
                "effectiveness_checked": True,
                "effectiveness_notes": "Ne doit pas être persisté.",
            },
        )

    with SessionLocal() as db:
        action = db.get(CorrectiveAction, action_id)
        assert action is not None
        assert action.status == "planned"
        assert action.effectiveness_checked is False
        assert action.effectiveness_notes is None
        assert action.completed_at is None
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "quality.capa.update",
                AuditEvent.entity_id == str(action_id),
            )
            .count()
            == 0
        )


def test_nc_transition_rolls_back_when_audit_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _auth(client)
    nc_id = _create_nc(client, headers)
    monkeypatch.setattr(quality_endpoint, "log_audit_event", _fail_capa_update)

    with pytest.raises(RuntimeError, match="synthetic quality audit failure"):
        client.post(
            f"/api/v1/quality/non-conformities/{nc_id}/transition",
            headers=headers,
            json={"status": "analysis"},
        )

    with SessionLocal() as db:
        nc = db.get(NonConformity, nc_id)
        assert nc is not None
        assert nc.status == "open"
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "quality.nc.transition",
                AuditEvent.entity_id == str(nc_id),
            )
            .count()
            == 0
        )

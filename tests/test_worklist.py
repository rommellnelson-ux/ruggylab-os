"""Tests — Ma file de travail opérationnelle."""

from __future__ import annotations

import datetime as dt
import uuid

import app.db.session as db_session
from app.models import NonConformity, QcControl, QcResult, Result, Sample
from app.utils.datetime_utils import utcnow_naive


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _patient_sample(client, headers: dict[str, str], *, status: str = "Recu") -> int:
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"WL-{_uid()}",
            "first_name": "Work",
            "last_name": "List",
            "birth_date": "1980-01-01",
            "sex": "F",
        },
    )
    assert patient.status_code == 201, patient.text
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": f"WL-{_uid()}", "patient_id": patient.json()["id"], "status": status},
    )
    assert sample.status_code == 201, sample.text
    return sample.json()["id"]


def test_worklist_requires_auth(client) -> None:
    response = client.get("/api/v1/worklist/my")
    assert response.status_code == 401


def test_worklist_empty_state_when_no_operational_items(client) -> None:
    headers = _auth(client)
    response = client.get("/api/v1/worklist/my", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"] == []
    assert payload["summary"] == {
        "total": 0,
        "critical": 0,
        "overdue": 0,
        "urgent": 0,
        "blocked": 0,
    }


def test_worklist_aggregates_priority_items(client) -> None:
    headers = _auth(client)
    client.post(
        "/api/v1/tat/targets",
        headers=headers,
        json={"exam_code": "WLTAT", "label": "TAT worklist", "target_minutes": 30},
    )

    sample_critical = _patient_sample(client, headers)
    critical = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_critical,
            "exam_code": "NFS",
            "data_points": {"HGB": 4.2},
            "is_critical": True,
        },
    )
    assert critical.status_code == 201, critical.text

    sample_tat = _patient_sample(client, headers)
    tat = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_tat,
            "exam_code": "WLTAT",
            "data_points": {"GLU": 5.2},
            "is_critical": False,
        },
    )
    assert tat.status_code == 201, tat.text

    db = db_session.SessionLocal()
    try:
        now = utcnow_naive()
        critical_result = db.get(Result, critical.json()["id"])
        assert critical_result is not None
        critical_result.analysis_date = now - dt.timedelta(minutes=35)
        tat_result = db.get(Result, tat.json()["id"])
        assert tat_result is not None
        tat_result.registered_at = now - dt.timedelta(minutes=45)
        tat_result.bio_validated_at = None

        control = QcControl(
            analyte="HGB", level="Niveau 1", unit="g/dL", target_mean=12, target_sd=1
        )
        db.add(control)
        db.flush()
        db.add(
            QcResult(
                control_id=control.id,
                value=20,
                measured_at=dt.date.today(),
                operator="QA",
                violations='["1-3s"]',
            )
        )
        db.add(
            NonConformity(
                title="CAPA en retard",
                source="qc",
                severity="major",
                status="action",
                due_date=now - dt.timedelta(days=1),
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/worklist/my", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    categories = {item["category"] for item in payload["items"]}
    assert {"critical", "tat", "qc", "quality"}.issubset(categories)
    assert payload["summary"]["critical"] >= 1
    assert payload["summary"]["overdue"] >= 1
    assert payload["items"][0]["priority"] in {"critical", "overdue"}
    assert any(action["label"] == "Prendre en charge" for action in payload["items"][0]["actions"])
    quality_items = [item for item in payload["items"] if item["category"] == "quality"]
    assert quality_items
    assert all(
        action["label"] != "Clôturer" for item in quality_items for action in item["actions"]
    )


def test_worklist_category_filter(client) -> None:
    headers = _auth(client)
    sample_id = _patient_sample(client, headers)
    client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "exam_code": "NFS",
            "data_points": {"HGB": 4.2},
            "is_critical": True,
        },
    )

    response = client.get("/api/v1/worklist/my?category=critical", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["items"]
    assert {item["category"] for item in response.json()["items"]} == {"critical"}


def test_worklist_uat_field_scenarios_and_source_deep_links(client) -> None:
    headers = _auth(client)
    client.post(
        "/api/v1/tat/targets",
        headers=headers,
        json={"exam_code": "WLUAT", "label": "TAT UAT terrain", "target_minutes": 30},
    )

    critical_sample_id = _patient_sample(client, headers)
    critical = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": critical_sample_id,
            "exam_code": "NFS",
            "data_points": {"HGB": 4.1},
            "is_critical": True,
        },
    )
    assert critical.status_code == 201, critical.text

    tat_sample_id = _patient_sample(client, headers)
    tat = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": tat_sample_id,
            "exam_code": "WLUAT",
            "data_points": {"GLU": 5.2},
            "is_critical": False,
        },
    )
    assert tat.status_code == 201, tat.text

    blocked_sample_id = _patient_sample(client, headers, status="Annule")

    db = db_session.SessionLocal()
    try:
        now = utcnow_naive()
        critical_result = db.get(Result, critical.json()["id"])
        assert critical_result is not None
        critical_result.analysis_date = now - dt.timedelta(minutes=40)

        tat_result = db.get(Result, tat.json()["id"])
        assert tat_result is not None
        tat_result.registered_at = now - dt.timedelta(minutes=20)
        tat_result.bio_validated_at = None

        blocked_sample = db.get(Sample, blocked_sample_id)
        assert blocked_sample is not None
        blocked_sample.collection_date = now - dt.timedelta(minutes=25)

        control = QcControl(
            analyte="UAT-HGB", level="Niveau 2", unit="g/dL", target_mean=12, target_sd=1
        )
        db.add(control)
        db.flush()
        db.add(
            QcResult(
                control_id=control.id,
                value=16,
                measured_at=dt.date.today(),
                operator="UAT",
                violations='["1-3s"]',
            )
        )
        nc = NonConformity(
            title="UAT CAPA en retard",
            source="qc",
            severity="major",
            status="action",
            due_date=now - dt.timedelta(days=2),
        )
        db.add(nc)
        db.commit()
        control_id = control.id
        nc_id = nc.id
    finally:
        db.close()

    response = client.get("/api/v1/worklist/my", headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    by_id = {item["id"]: item for item in items}
    qc_item = next(
        item for item in items if item["category"] == "qc" and "UAT-HGB" in item["title"]
    )

    assert by_id[f"critical:{critical.json()['id']}"]["priority"] == "critical"
    assert by_id[f"tat:{tat.json()['id']}"]["priority"] == "urgent"
    assert by_id[f"sample:{blocked_sample_id}"]["priority"] == "blocked"
    assert qc_item["status"] == "rejet Westgard"
    assert by_id[f"nc:{nc_id}"]["priority"] == "overdue"

    assert any(
        action["path"] == f"#/results?result={critical.json()['id']}"
        for action in by_id[f"critical:{critical.json()['id']}"]["actions"]
    )
    assert by_id[f"sample:{blocked_sample_id}"]["actions"][0]["path"] == (
        f"#/samples?sample={blocked_sample_id}"
    )
    assert qc_item["actions"][0]["path"] == f"#/qc?control={control_id}"
    assert by_id[f"nc:{nc_id}"]["actions"][0]["path"] == f"#/quality?nc={nc_id}"

    filtered = client.get("/api/v1/worklist/my?category=sample", headers=headers)
    assert filtered.status_code == 200, filtered.text
    assert {item["category"] for item in filtered.json()["items"]} == {"sample"}

    ack = client.patch(
        f"/api/v1/results/{critical.json()['id']}/ack-critical",
        headers=headers,
    )
    assert ack.status_code == 200, ack.text
    refreshed = client.get("/api/v1/worklist/my?category=critical", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    assert all(
        item["id"] != f"critical:{critical.json()['id']}" for item in refreshed.json()["items"]
    )

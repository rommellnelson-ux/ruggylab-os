"""Tests — Vue Paillasse / Bench Radar."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

import app.db.session as db_session
from app.models import Result
from app.utils.datetime_utils import utcnow_naive


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_patient_sample(client, headers: dict[str, str], prefix: str) -> int:
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"{prefix}-IPP-{_uid()}",
            "first_name": "Bench",
            "last_name": "Radar",
            "birth_date": "1985-01-01",
            "sex": "F",
        },
    )
    assert patient.status_code == 201, patient.text
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": f"{prefix}-SMP-{_uid()}",
            "patient_id": patient.json()["id"],
            "status": "Recu",
        },
    )
    assert sample.status_code == 201, sample.text
    return sample.json()["id"]


def _make_result(
    client,
    headers: dict[str, str],
    *,
    sample_id: int,
    exam_code: str,
    is_critical: bool = False,
) -> int:
    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "exam_code": exam_code,
            "data_points": {"HGB": 4.8 if is_critical else 12.4},
            "is_critical": is_critical,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_bench_radar_prefilters_critical_tat_and_routine(client) -> None:
    headers = _auth(client)
    client.post(
        "/api/v1/tat/targets",
        headers=headers,
        json={"exam_code": "NFS", "label": "NFS bench", "target_minutes": 30},
    )

    critical_id = _make_result(
        client,
        headers,
        sample_id=_make_patient_sample(client, headers, "CRIT"),
        exam_code="NFS",
        is_critical=True,
    )
    tat_id = _make_result(
        client,
        headers,
        sample_id=_make_patient_sample(client, headers, "TAT"),
        exam_code="NFS",
    )
    routine_id = _make_result(
        client,
        headers,
        sample_id=_make_patient_sample(client, headers, "ROUT"),
        exam_code="ROUTINE",
    )
    hidden_id = _make_result(
        client,
        headers,
        sample_id=_make_patient_sample(client, headers, "DONE"),
        exam_code="DONE",
    )

    db = db_session.SessionLocal()
    try:
        now = utcnow_naive()
        tat = db.get(Result, tat_id)
        routine = db.get(Result, routine_id)
        hidden = db.get(Result, hidden_id)
        assert tat is not None
        assert routine is not None
        assert hidden is not None
        tat.registered_at = now - dt.timedelta(minutes=20)
        tat.bio_validated_at = None
        routine.bio_validated_at = None
        hidden.bio_validated_at = now
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/bench/radar", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["result_id"] for item in payload["criticals"]] == [critical_id]
    assert [item["result_id"] for item in payload["tat_expiring"]] == [tat_id]
    assert [item["result_id"] for item in payload["routine"]] == [routine_id]
    assert payload["criticals"][0]["guidance"]["preanalytics"]["container"] == "Tube EDTA violet"
    assert payload["tat_expiring"][0]["guidance"]["preanalytics"]["bench"] == "Hematologie"
    assert hidden_id not in {item["result_id"] for item in payload["routine"]}


def test_bench_radar_requires_auth(client) -> None:
    response = client.get("/api/v1/bench/radar")
    assert response.status_code == 401


def test_bench_template_contains_fat_finger_guards() -> None:
    html = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "bench_radar.html"
    ).read_text(encoding="utf-8")
    assert "tbody tr:nth-child(odd)" in html
    assert "position: sticky" in html
    assert "critical_value_alert" in html
    assert "scheduleReconnect" in html
    assert "2 ** Math.min(reconnectAttempt, 5)" in html
    assert "guidanceLine" in html
    assert "/api/v1/bench/radar" not in html
    assert "`${API_PREFIX}/bench/radar`" in html

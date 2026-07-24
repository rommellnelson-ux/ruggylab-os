"""Régressions de cloisonnement du tableau de bord épidémiologique."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi.testclient import TestClient

DASHBOARD_URL = "/api/v1/epidemiology/dashboard"


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _admin(client: TestClient) -> dict[str, str]:
    return _login(client, "admin", "change_me_admin_password")


def _user(
    client: TestClient,
    admin: dict[str, str],
    *,
    role: str,
    unit: str | None = None,
) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    username = f"epid-scope-{role}-{suffix}"
    password = "SyntheticPass123!"
    payload = {"username": username, "password": password, "role": role}
    if unit is not None:
        payload["unit"] = unit
    response = client.post("/api/v1/users", headers=admin, json=payload)
    assert response.status_code in (200, 201), response.text
    return _login(client, username, password)


def _result(
    client: TestClient,
    admin: dict[str, str],
    *,
    unit: str | None,
    value: float,
) -> int:
    suffix = uuid.uuid4().hex[:8]
    patient_payload = {
        "ipp_unique_id": f"EPID-SCOPE-{suffix}",
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
            "barcode": f"EPID-SCOPE-S-{suffix}",
            "patient_id": patient_response.json()["id"],
            "status": "Recu",
        },
    )
    assert sample_response.status_code == 201, sample_response.text
    result_response = client.post(
        "/api/v1/results",
        headers=admin,
        json={
            "sample_id": sample_response.json()["id"],
            "data_points": {
                "SYNTHETIC": {
                    "value": value,
                    "unit": "synthetic-unit",
                    "status": "NORMAL",
                }
            },
            "is_critical": False,
        },
    )
    assert result_response.status_code == 201, result_response.text
    return int(result_response.json()["id"])


def test_unit_technician_dashboard_excludes_other_unit_aggregates(
    client: TestClient,
) -> None:
    admin = _admin(client)
    _result(client, admin, unit="hematologie", value=10.0)
    _result(client, admin, unit="biochimie", value=999.0)
    _result(client, admin, unit=None, value=30.0)
    technician = _user(client, admin, role="technician", unit="hematologie")
    today = dt.date.today().isoformat()

    response = client.post(
        DASHBOARD_URL,
        headers=technician,
        json={"start_date": today, "end_date": today},
    )

    assert response.status_code == 200, response.text
    assert response.json()["total_results"] == 2
    synthetic_stats = next(
        row for row in response.json()["parameter_stats"] if row["parameter"] == "SYNTHETIC"
    )
    assert synthetic_stats["total_results"] == 2
    assert synthetic_stats["mean_value"] == 20.0

    admin_response = client.post(
        DASHBOARD_URL,
        headers=admin,
        json={"start_date": today, "end_date": today},
    )
    assert admin_response.status_code == 200, admin_response.text
    assert admin_response.json()["total_results"] == 3


def test_accountant_cannot_read_epidemiology_dashboard(client: TestClient) -> None:
    admin = _admin(client)
    accountant = _user(client, admin, role="accountant")

    response = client.post(DASHBOARD_URL, headers=accountant, json={})

    assert response.status_code == 403

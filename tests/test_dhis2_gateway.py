import datetime as dt

import app.db.session as db_session
from app.models import Patient, Result, Sample


def _auth(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_month_data() -> None:
    db = db_session.SessionLocal()
    try:
        patient = Patient(
            ipp_unique_id="IPP-DHIS2-001",
            first_name="Patient",
            last_name="Synthétique",
            birth_date=dt.date(1990, 1, 1),
            sex="F",
        )
        db.add(patient)
        db.flush()
        normal_sample = Sample(
            barcode="DHIS2-NORMAL",
            patient_id=patient.id,
            collection_date=dt.datetime(2026, 7, 2, 8),
            status="received",
        )
        rejected_sample = Sample(
            barcode="DHIS2-REJECTED",
            patient_id=patient.id,
            collection_date=dt.datetime(2026, 7, 3, 8),
            status="rejected",
        )
        db.add_all([normal_sample, rejected_sample])
        db.flush()
        db.add_all(
            [
                Result(
                    sample_id=normal_sample.id,
                    analysis_date=dt.datetime(2026, 7, 2, 9),
                    exam_code="NFS",
                    data_points={"HGB": {"value": 12.5, "unit": "g/dL"}},
                    is_validated=True,
                ),
                Result(
                    sample_id=normal_sample.id,
                    analysis_date=dt.datetime(2026, 7, 2, 10),
                    exam_code="GE",
                    data_points={"MALARIA": "positif"},
                    is_validated=True,
                    is_critical=True,
                    critical_ack_at=dt.datetime(2026, 7, 2, 10, 5),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def _create_mappings(client, headers) -> None:
    for index, code in enumerate(
        [
            "LAB_ACT_TOTAL",
            "MAL_TEST_TOTAL",
            "MAL_POS_TOTAL",
            "PRE_REJECT_TOTAL",
            "CRIT_NOTIFIED",
        ],
        start=1,
    ):
        response = client.post(
            "/api/v1/integrations/dhis2/mappings",
            headers=headers,
            json={
                "internal_code": code,
                "data_element_uid": f"DataElem{index:03d}",
                "data_set_uid": "DataSet0001",
                "org_unit_uid": "OrgUnit0001",
            },
        )
        assert response.status_code == 201, response.text


def test_preview_contains_only_aggregate_values(client) -> None:
    headers = _auth(client)
    _seed_month_data()
    _create_mappings(client, headers)

    response = client.get(
        "/api/v1/integrations/dhis2/preview",
        headers=headers,
        params={
            "period": "202607",
            "data_set_uid": "DataSet0001",
            "org_unit_uid": "OrgUnit0001",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    values = {item["code"]: item["value"] for item in payload["indicators"]}
    assert values == {
        "LAB_ACT_TOTAL": 2,
        "MAL_TEST_TOTAL": 1,
        "MAL_POS_TOTAL": 1,
        "PRE_REJECT_TOTAL": 1,
        "CRIT_NOTIFIED": 1,
    }
    serialized = response.text.lower()
    assert "ipp-dhis2" not in serialized
    assert "synthétique" not in serialized
    assert "dhis2-normal" not in serialized


def test_export_is_idempotent_validated_and_downloadable(client) -> None:
    headers = _auth(client)
    _seed_month_data()
    _create_mappings(client, headers)
    request = {
        "period": "202607",
        "data_set_uid": "DataSet0001",
        "org_unit_uid": "OrgUnit0001",
    }
    first = client.post("/api/v1/integrations/dhis2/exports", headers=headers, json=request)
    second = client.post("/api/v1/integrations/dhis2/exports", headers=headers, json=request)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    export_id = first.json()["id"]
    validated = client.post(
        f"/api/v1/integrations/dhis2/exports/{export_id}/validate",
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.json()["status"] == "VALIDATED"

    csv_response = client.get(
        f"/api/v1/integrations/dhis2/exports/{export_id}.csv",
        headers=headers,
    )
    assert csv_response.status_code == 200
    assert "dataElement" in csv_response.text
    assert "IPP-DHIS2" not in csv_response.text


def test_export_requires_complete_mapping(client) -> None:
    headers = _auth(client)
    response = client.post(
        "/api/v1/integrations/dhis2/exports",
        headers=headers,
        json={
            "period": "202607",
            "data_set_uid": "DataSet0001",
            "org_unit_uid": "OrgUnit0001",
        },
    )
    assert response.status_code == 422
    assert "Mappings DHIS2 incomplets" in response.text

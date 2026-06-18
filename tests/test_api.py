from datetime import UTC, datetime, timedelta


def _login(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth_headers(
    client, username: str = "admin", password: str = "change_me_admin_password"
) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, username, password)}"}


def test_cockpit_ui_is_served(client) -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert "RuggyLab OS" in response.text
    assert "/api/v1/login/access-token" in response.text
    assert 'API_PREFIX = "/api/v1"' in response.text
    assert "/stock/notify" in response.text
    assert "/billing/bnpl/schedule" in response.text
    assert "/api/v1/prescription/report" in response.text
    assert "normalizeApiPath" in response.text


def test_login_with_seeded_admin(client) -> None:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]


def test_patients_pagination_and_search(client) -> None:
    headers = _auth_headers(client)

    create_first = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-001",
            "first_name": "Aminata",
            "last_name": "Konan",
            "birth_date": "1990-04-10",
            "sex": "F",
            "rank": "Capitaine",
        },
    )
    assert create_first.status_code == 201, create_first.text
    create_second = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-002",
            "first_name": "Koffi",
            "last_name": "Yao",
            "birth_date": "1988-09-01",
            "sex": "M",
            "rank": "Lieutenant",
        },
    )
    assert create_second.status_code == 201, create_second.text

    response = client.get(
        "/api/v1/patients",
        headers=headers,
        params={"skip": 0, "limit": 1, "q": "Aminata"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 1
    assert data["meta"]["limit"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["first_name"] == "Aminata"

    me = client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_results_pagination_and_filters(client) -> None:
    headers = _auth_headers(client)

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-003",
            "first_name": "Jean",
            "last_name": "Doe",
            "birth_date": "1985-01-01",
            "sex": "M",
            "rank": "Civil",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    patient_id = patient_response.json()["id"]

    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "SAMPLE-001", "patient_id": patient_id, "status": "Recu"},
    )
    assert sample_response.status_code == 201, sample_response.text
    sample_id = sample_response.json()["id"]

    equipment_response = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DH36", "serial_number": "DH36-001", "type": "Automate"},
    )
    assert equipment_response.status_code == 201, equipment_response.text
    equipment_id = equipment_response.json()["id"]

    first_result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment_id,
            "data_points": {"WBC": 5.2},
            "is_critical": False,
        },
    )
    assert first_result.status_code == 201, first_result.text
    second_result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment_id,
            "data_points": {"WBC": 25.0},
            "is_critical": True,
        },
    )
    assert second_result.status_code == 201, second_result.text

    response = client.get(
        "/api/v1/results",
        headers=headers,
        params={"sample_id": sample_id, "is_critical": "true"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["is_critical"] is True


def test_result_detail_includes_patient_sample_and_bioref(client) -> None:
    headers = _auth_headers(client)

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-DETAIL-001",
            "first_name": "Detail",
            "last_name": "Patient",
            "birth_date": "1991-02-03",
            "sex": "F",
            "rank": "Capitaine",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    patient = patient_response.json()

    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "DETAIL-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    )
    assert sample_response.status_code == 201, sample_response.text
    sample = sample_response.json()

    result_response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "data_points": {"WBC": 5.2},
            "is_critical": False,
            "exam_code": "NFS",
        },
    )
    assert result_response.status_code == 201, result_response.text
    result = result_response.json()

    detail_response = client.get(f"/api/v1/results/{result['id']}/detail", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["result"]["id"] == result["id"]
    assert detail["sample"]["barcode"] == "DETAIL-SAMPLE-001"
    assert detail["patient"]["ipp_unique_id"] == "IPP-DETAIL-001"
    assert detail["bioref"]["exam_code"] == "NFS"


def test_results_cockpit_returns_enriched_rows(client) -> None:
    headers = _auth_headers(client)

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-COCKPIT-001",
            "first_name": "Cockpit",
            "last_name": "Patient",
            "birth_date": "1992-01-02",
            "sex": "F",
            "rank": "Major",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    patient = patient_response.json()

    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "COCKPIT-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    )
    assert sample_response.status_code == 201, sample_response.text
    sample = sample_response.json()

    result_response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "data_points": {"CRP": 7.5},
            "is_critical": False,
            "exam_code": "CRP",
        },
    )
    assert result_response.status_code == 201, result_response.text
    result = result_response.json()

    response = client.get("/api/v1/results/cockpit?limit=20", headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()
    row = next(item for item in items if item["result"]["id"] == result["id"])
    assert row["sample"]["barcode"] == "COCKPIT-SAMPLE-001"
    assert row["patient"]["ipp_unique_id"] == "IPP-COCKPIT-001"


def test_ack_critical_batch_and_clinical_audit(client) -> None:
    headers = _auth_headers(client)

    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-BATCH-001",
            "first_name": "Batch",
            "last_name": "Critical",
            "birth_date": "1988-03-04",
            "sex": "M",
            "rank": "Sergent",
        },
    ).json()
    first_sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BATCH-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    second_sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BATCH-SAMPLE-002", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    critical = client.post(
        "/api/v1/results",
        headers=headers,
        json={"sample_id": first_sample["id"], "data_points": {"K": 7.2}, "is_critical": True},
    ).json()
    normal = client.post(
        "/api/v1/results",
        headers=headers,
        json={"sample_id": second_sample["id"], "data_points": {"K": 4.2}, "is_critical": False},
    ).json()

    response = client.patch(
        "/api/v1/results/ack-critical-batch",
        headers=headers,
        json={"result_ids": [critical["id"], normal["id"], 999999]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["acknowledged"] == [critical["id"]]
    assert payload["skipped"][str(normal["id"])] == "non critique"
    assert payload["skipped"]["999999"] == "introuvable"

    detail = client.get(f"/api/v1/results/{critical['id']}", headers=headers).json()
    assert detail["critical_ack_at"] is not None
    audit_response = client.get(f"/api/v1/results/{critical['id']}/clinical-audit", headers=headers)
    assert audit_response.status_code == 200, audit_response.text
    assert any(event["event_type"] == "result.critical_ack" for event in audit_response.json())


def test_critical_compliance_report_and_export(client) -> None:
    headers = _auth_headers(client)

    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-CRIT-COMP-001",
            "first_name": "Conformite",
            "last_name": "Critique",
            "birth_date": "1984-05-06",
            "sex": "F",
            "rank": "Commandant",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "CRIT-COMP-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    client.patch(
        f"/api/v1/patients/{patient['id']}",
        headers=headers,
        json={"unit": "Urgences"},
    )
    handled_result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "data_points": {"K": 7.1},
            "is_critical": True,
            "exam_code": "IONO",
        },
    ).json()
    pending_result = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "analysis_date": (datetime.now(UTC) - timedelta(minutes=45)).isoformat(),
            "data_points": {"CRP": 320},
            "is_critical": True,
            "exam_code": "CRP",
        },
    ).json()

    ack_response = client.patch(
        f"/api/v1/results/{handled_result['id']}/ack-critical",
        headers=headers,
    )
    assert ack_response.status_code == 200, ack_response.text

    report_response = client.get(
        "/api/v1/reports/critical-compliance?days=30&target_minutes=30",
        headers=headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["critical_total"] >= 2
    assert report["critical_handled"] >= 1
    assert report["critical_pending"] >= 1
    assert report["target_minutes"] == 30
    assert report["filters"] == {"exam_code": None, "unit": None}
    assert report["critical_late"] >= 1
    assert "on_time_rate_pct" in report
    assert report["summary"]["top_exams"]
    assert any(item["label"] == "CRP" for item in report["summary"]["top_exams"])
    assert any(item["label"] == "Urgences" for item in report["summary"]["by_unit"])

    rows_by_id = {row["result_id"]: row for row in report["rows"]}
    assert rows_by_id[handled_result["id"]]["status"] == "pris_en_charge"
    assert rows_by_id[handled_result["id"]]["ack_by"] == "RuggyLab Administrator"
    assert rows_by_id[handled_result["id"]]["sample_barcode"] == "CRIT-COMP-SAMPLE-001"
    assert rows_by_id[handled_result["id"]]["patient_ipp"] == "IPP-CRIT-COMP-001"
    assert rows_by_id[handled_result["id"]]["unit"] == "Urgences"
    assert rows_by_id[pending_result["id"]]["status"] == "en_attente"
    assert rows_by_id[pending_result["id"]]["compliance_status"] == "hors_delai"

    filtered_response = client.get(
        "/api/v1/reports/critical-compliance?days=30&target_minutes=30&exam_code=CRP&unit=Urgences",
        headers=headers,
    )
    assert filtered_response.status_code == 200, filtered_response.text
    filtered = filtered_response.json()
    assert filtered["filters"] == {"exam_code": "CRP", "unit": "Urgences"}
    assert {row["result_id"] for row in filtered["rows"]} == {pending_result["id"]}

    csv_response = client.get(
        "/api/v1/reports/critical-compliance/export.csv?days=30&target_minutes=30",
        headers=headers,
    )
    assert csv_response.status_code == 200, csv_response.text
    assert "text/csv" in csv_response.headers["content-type"]
    assert "result_id,analysis_date,critical_ack_at,ack_delay_minutes" in csv_response.text
    assert "compliance_status" in csv_response.text
    assert "RuggyLab Administrator" in csv_response.text
    assert "Urgences" in csv_response.text
    assert "CRIT-COMP-SAMPLE-001" in csv_response.text


def test_critical_workflow_multi_role_permissions(client) -> None:
    admin_headers = _auth_headers(client)

    tech_user = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": "crit_tech",
            "password": "TechPass123!",
            "role": "technician",
            "full_name": "Technicien Critique",
        },
    )
    assert tech_user.status_code == 201, tech_user.text
    tech_headers = _auth_headers(client, "crit_tech", "TechPass123!")

    patient = client.post(
        "/api/v1/patients",
        headers=admin_headers,
        json={
            "ipp_unique_id": "IPP-CRIT-ROLE-001",
            "first_name": "Role",
            "last_name": "Critique",
            "birth_date": "1984-05-06",
            "sex": "F",
            "rank": "Commandant",
            "unit": "Biochimie",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=admin_headers,
        json={"barcode": "CRIT-ROLE-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    critical = client.post(
        "/api/v1/results",
        headers=admin_headers,
        json={
            "sample_id": sample["id"],
            "analysis_date": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
            "data_points": {"K": 7.1},
            "is_critical": True,
            "exam_code": "IONO",
        },
    ).json()

    report_as_tech = client.get(
        "/api/v1/reports/critical-compliance?days=30&unit=Biochimie",
        headers=tech_headers,
    )
    assert report_as_tech.status_code == 200, report_as_tech.text
    assert report_as_tech.json()["critical_pending"] >= 1

    ack_as_tech = client.patch(
        f"/api/v1/results/{critical['id']}/ack-critical",
        headers=tech_headers,
    )
    assert ack_as_tech.status_code == 200, ack_as_tech.text

    report_after_ack = client.get(
        "/api/v1/reports/critical-compliance?days=30&unit=Biochimie",
        headers=tech_headers,
    ).json()
    row = next(row for row in report_after_ack["rows"] if row["result_id"] == critical["id"])
    assert row["ack_by"] == "Technicien Critique"
    assert row["status"] == "pris_en_charge"

    audit_as_tech = client.get("/api/v1/audit-events", headers=tech_headers)
    assert audit_as_tech.status_code == 403
    audit_as_admin = client.get(
        "/api/v1/audit-events?event_type=result.critical_ack",
        headers=admin_headers,
    )
    assert audit_as_admin.status_code == 200
    assert any(
        event["entity_id"] == str(critical["id"]) for event in audit_as_admin.json()["items"]
    )


def test_result_history_returns_comparable_patient_results(client) -> None:
    headers = _auth_headers(client)

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-HISTORY-001",
            "first_name": "History",
            "last_name": "Patient",
            "birth_date": "1987-06-01",
            "sex": "M",
            "rank": "Adjudant",
        },
    )
    assert patient_response.status_code == 201, patient_response.text
    patient = patient_response.json()

    first_sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "HISTORY-SAMPLE-001", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    second_sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "HISTORY-SAMPLE-002", "patient_id": patient["id"], "status": "Recu"},
    ).json()

    previous = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": first_sample["id"],
            "data_points": {"WBC": 5.0, "HGB": 12.0},
            "is_critical": False,
            "exam_code": "NFS",
        },
    )
    assert previous.status_code == 201, previous.text
    current = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": second_sample["id"],
            "data_points": {"WBC": 8.5, "HGB": 11.0},
            "is_critical": False,
            "exam_code": "NFS",
        },
    )
    assert current.status_code == 201, current.text
    current_result = current.json()

    response = client.get(f"/api/v1/results/{current_result['id']}/history", headers=headers)
    assert response.status_code == 200, response.text
    history = response.json()
    assert history["patient_id"] == patient["id"]
    assert history["exam_code"] == "NFS"
    assert len(history["items"]) == 1
    item = history["items"][0]
    assert item["sample"]["barcode"] == "HISTORY-SAMPLE-001"
    assert item["shared_analytes"] == ["HGB", "WBC"]
    assert item["delta_from_current"]["WBC"] == 3.5
    assert item["delta_from_current"]["HGB"] == -1.0


def test_create_user_requires_admin_token(client) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "username": "tech1",
            "password": "password123",
            "full_name": "Tech User",
            "role": "technician",
        },
    )
    assert response.status_code == 401

    token = _login(client, "admin", "change_me_admin_password")
    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "tech1",
            "password": "password123",
            "full_name": "Tech User",
            "role": "technician",
        },
    )
    assert response.status_code == 201
    assert response.json()["username"] == "tech1"


def test_sensitive_crud_endpoints_require_authentication(client) -> None:
    patient_response = client.post(
        "/api/v1/patients",
        json={
            "ipp_unique_id": "IPP-SEC-001",
            "first_name": "Anon",
            "last_name": "Attempt",
            "birth_date": "1990-01-01",
            "sex": "F",
            "rank": "Civil",
        },
    )
    assert patient_response.status_code == 401

    assert client.get("/api/v1/patients").status_code == 401
    assert (
        client.post(
            "/api/v1/samples", json={"barcode": "SAMPLE-SEC-001", "patient_id": 1}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/samples").status_code == 401
    assert (
        client.post(
            "/api/v1/equipments", json={"name": "DH36", "serial_number": "SEC-001"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/equipments").status_code == 401
    assert client.get("/api/v1/reagents").status_code == 401
    assert client.get("/api/v1/reagents/1").status_code == 401
    assert (
        client.post(
            "/api/v1/results", json={"sample_id": 1, "data_points": {"WBC": 6.1}}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/results").status_code == 401


def test_create_result_uses_authenticated_user_for_validation_fields(client) -> None:
    headers = _auth_headers(client)

    patient_response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-004",
            "first_name": "Louise",
            "last_name": "Martin",
            "birth_date": "1993-03-12",
            "sex": "F",
            "rank": "Caporal",
        },
    )
    patient_id = patient_response.json()["id"]
    sample_id = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "SAMPLE-002", "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]
    equipment_id = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DX5", "serial_number": "DX5-002", "type": "Automate"},
    ).json()["id"]

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment_id,
            "data_points": {"WBC": 7.4},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    # Server sets validator_id from authenticated user, not from client input
    assert payload["validator_id"] == 1
    assert payload["is_validated"] is True


def test_patient_sample_and_equipment_business_validation(client) -> None:
    headers = _auth_headers(client)

    future_patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-FUTURE",
            "first_name": "Future",
            "last_name": "Patient",
            "birth_date": "2999-01-01",
            "sex": "F",
        },
    )
    assert future_patient.status_code == 422

    invalid_sex = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-SEX",
            "first_name": "Invalid",
            "last_name": "Sex",
            "birth_date": "1990-01-01",
            "sex": "X",
        },
    )
    assert invalid_sex.status_code == 422

    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-VALIDATION",
            "first_name": "Valid",
            "last_name": "Patient",
            "birth_date": "1990-01-01",
            "sex": "m",
        },
    )
    assert patient.status_code == 201
    assert patient.json()["sex"] == "M"

    invalid_sample_status = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "SAMPLE-INVALID-STATUS",
            "patient_id": patient.json()["id"],
            "status": "Lost",
        },
    )
    assert invalid_sample_status.status_code == 422

    invalid_sample_dates = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "SAMPLE-INVALID-DATES",
            "patient_id": patient.json()["id"],
            "collection_date": "2026-01-02T10:00:00",
            "received_date": "2026-01-01T10:00:00",
            "status": "Recu",
        },
    )
    assert invalid_sample_dates.status_code == 422

    future_calibration = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Future Calibration",
            "serial_number": "FUT-CAL-1",
            "last_calibration": "2999-01-01",
        },
    )
    assert future_calibration.status_code == 422

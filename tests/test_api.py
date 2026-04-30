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
            "validator_id": 999,
            "is_validated": False,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
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

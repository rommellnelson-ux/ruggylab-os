def _login(
    client, username: str = "admin", password: str = "change_me_admin_password"
) -> str:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client)}"}


def _create_patient_sample_equipment(client) -> None:
    headers = _auth_headers(client)
    client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-900",
            "first_name": "Mariame",
            "last_name": "Test",
            "birth_date": "1992-06-15",
            "sex": "F",
            "rank": "Sergent",
        },
    )
    patient_id = client.get("/api/v1/patients", headers=headers).json()["items"][0][
        "id"
    ]
    client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BAR-900", "patient_id": patient_id, "status": "Recu"},
    )
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Precis Expert", "serial_number": "PE-900", "type": "POCT"},
    )
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Magnus Theia-i", "serial_number": "MAG-1", "type": "Microscope"},
    )


def _dh36_message(barcode: str, message_id: str, serial: str = "DH36-ING-001") -> str:
    return "\r".join(
        [
            f"MSH|^~\\&|{serial}|LAB|RUGGYLAB|LAB|20260429183000||ORU^R01|{message_id}|P|2.3",
            "PID|||IPP-DH36-001||Battle^Ready",
            f"OBR|1||{barcode}||CBC",
            "OBX|1|NM|WBC||6.1|10^9/L",
            "OBX|2|NM|RBC||4.7|10^12/L",
            "OBX|3|NM|HGB||132|g/L",
            "OBX|4|NM|HCT||40|%",
            "OBX|5|NM|MCV||86|fL",
            "OBX|6|NM|MCH||29|pg",
            "OBX|7|NM|MCHC||330|g/L",
            "OBX|8|NM|PLT||250|10^9/L",
        ]
    )


def test_precis_expert_endpoint_creates_result_and_audit_event(client) -> None:
    _create_patient_sample_equipment(client)
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/results/precis-expert",
        headers=headers,
        json={
            "sample_barcode": "BAR-900",
            "equipment_serial": "PE-900",
            "glucose_raw": 0.45,
            "cholesterol_raw": 1.8,
            "uric_acid_raw": 50.0,
            "lactate_raw": 1.2,
            "ketones_raw": 0.2,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_critical"] is True
    result_id = response.json()["result_id"]

    result_response = client.get(f"/api/v1/results/{result_id}", headers=headers)
    assert result_response.status_code == 200
    assert result_response.json()["is_validated"] is True

    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert any(
        event["event_type"] == "result.precis_expert.create"
        for event in audit_response.json()["items"]
    )


def test_imaging_endpoint_creates_reservation_and_audit_event(client) -> None:
    _create_patient_sample_equipment(client)
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": "BAR-900"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["image_url"].endswith(".jpg")

    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert any(
        event["event_type"] == "imaging.capture.reserve"
        for event in audit_response.json()["items"]
    )


def test_reagent_endpoint_and_audit_listing(client) -> None:
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Diluant DH36",
            "category": "hematology",
            "unit": "L",
            "current_stock": 12.5,
            "alert_threshold": 3.0,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Diluant DH36"

    list_response = client.get("/api/v1/reagents", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1

    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert any(
        event["event_type"] == "reagent.create"
        for event in audit_response.json()["items"]
    )


def test_reagent_crud_and_dashboards(client) -> None:
    headers = _auth_headers(client)
    client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-910",
            "first_name": "Alpha",
            "last_name": "Runner",
            "birth_date": "1991-01-10",
            "sex": "M",
            "rank": "Caporal",
        },
    )
    patient_id = client.get("/api/v1/patients", headers=headers).json()["items"][0][
        "id"
    ]
    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BAR-910", "patient_id": patient_id, "status": "Recu"},
    )
    sample_id = sample_response.json()["id"]
    equipment_response = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DH36", "serial_number": "DH36-910", "type": "Automate"},
    )
    equipment_id = equipment_response.json()["id"]

    create_response = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Lyse DH36",
            "category": "hematology",
            "unit": "L",
            "current_stock": 2.0,
            "alert_threshold": 3.0,
        },
    )
    assert create_response.status_code == 201, create_response.text
    reagent_id = create_response.json()["id"]

    client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Diluant DH36",
            "category": "hematology",
            "unit": "L",
            "current_stock": 12.0,
            "alert_threshold": 3.0,
        },
    )
    reagents = client.get("/api/v1/reagents", headers=headers).json()["items"]
    diluant_id = next(item["id"] for item in reagents if item["name"] == "Diluant DH36")
    ratio_response = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment_id,
            "reagent_id": reagent_id,
            "consumption_per_run": 0.0008,
            "adjustment_factor": 1.0,
            "notes": "Base lyse usage per run",
            "is_active": True,
        },
    )
    assert ratio_response.status_code == 201, ratio_response.text
    ratio_response = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment_id,
            "reagent_id": diluant_id,
            "consumption_per_run": 0.02,
            "adjustment_factor": 1.0,
            "notes": "Base diluant usage per run",
            "is_active": True,
        },
    )
    assert ratio_response.status_code == 201, ratio_response.text

    client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment_id,
            "data_points": {"WBC": 6.1},
            "is_critical": False,
        },
    )
    client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample_id,
            "equipment_id": equipment_id,
            "data_points": {"WBC": 8.9},
            "is_critical": False,
        },
    )

    update_response = client.put(
        f"/api/v1/reagents/{reagent_id}",
        headers=headers,
        json={
            "name": "Lyse DH36",
            "category": "hematology",
            "unit": "L",
            "current_stock": 5.0,
            "alert_threshold": 3.0,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_stock"] == 5.0

    stock_dashboard = client.get("/api/v1/reports/stock-dashboard", headers=headers)
    assert stock_dashboard.status_code == 200
    assert stock_dashboard.json()["total_reagents"] >= 1

    monthly_dashboard = client.get(
        "/api/v1/reports/monthly-consumption", headers=headers
    )
    assert monthly_dashboard.status_code == 200
    assert len(monthly_dashboard.json()["items"]) >= 1
    monthly_items = {
        item["reagent_name"]: item for item in monthly_dashboard.json()["items"]
    }
    assert monthly_items["Lyse DH36"]["estimated_monthly_consumption"] > 0
    assert monthly_items["Lyse DH36"]["actual_run_count"] == 2
    assert "Dymind DH36" in monthly_items["Lyse DH36"]["source_equipment"]
    ratio_list = client.get("/api/v1/equipment-reagent-ratios", headers=headers)
    assert ratio_list.status_code == 200
    assert ratio_list.json()["meta"]["total"] >= 2

    critical_dashboard = client.get(
        "/api/v1/reports/critical-thresholds", headers=headers
    )
    assert critical_dashboard.status_code == 200
    assert "total_critical_reagents" in critical_dashboard.json()

    audit_dashboard = client.get("/api/v1/reports/audit-dashboard", headers=headers)
    assert audit_dashboard.status_code == 200
    assert "event_type_breakdown" in audit_dashboard.json()

    delete_response = client.delete(f"/api/v1/reagents/{reagent_id}", headers=headers)
    assert delete_response.status_code == 409

    ratio_list = client.get("/api/v1/equipment-reagent-ratios", headers=headers).json()[
        "items"
    ]
    lyse_ratio = next(item for item in ratio_list if item["reagent_id"] == reagent_id)
    delete_ratio_response = client.delete(
        f"/api/v1/equipment-reagent-ratios/{lyse_ratio['id']}", headers=headers
    )
    assert delete_ratio_response.status_code == 200

    delete_response = client.delete(f"/api/v1/reagents/{reagent_id}", headers=headers)
    assert delete_response.status_code == 409


def test_validated_result_consumes_reagents_and_audits_movement(client) -> None:
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-STOCK-001",
            "first_name": "Stock",
            "last_name": "Runner",
            "birth_date": "1991-01-10",
            "sex": "M",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "BAR-STOCK-001",
            "patient_id": patient["id"],
            "status": "Recu",
        },
    ).json()
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Stock Analyzer",
            "serial_number": "STOCK-001",
            "type": "Automate",
        },
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Stock Reagent",
            "category": "hematology",
            "unit": "L",
            "current_stock": 1.0,
            "alert_threshold": 0.2,
        },
    ).json()
    client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 0.2,
            "adjustment_factor": 1.5,
            "is_active": True,
        },
    )

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "equipment_id": equipment["id"],
            "data_points": {"WBC": 6.1},
            "is_critical": False,
        },
    )
    assert response.status_code == 201, response.text

    updated_reagent = client.get(
        f"/api/v1/reagents/{reagent['id']}", headers=headers
    ).json()
    assert updated_reagent["current_stock"] == 0.7

    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert any(
        event["event_type"] == "stock.consume"
        and event["entity_id"] == str(reagent["id"])
        for event in audit_response.json()["items"]
    )


def test_inactive_ratio_does_not_consume_stock(client) -> None:
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-STOCK-002",
            "first_name": "Inactive",
            "last_name": "Ratio",
            "birth_date": "1991-01-10",
            "sex": "F",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "BAR-STOCK-002",
            "patient_id": patient["id"],
            "status": "Recu",
        },
    ).json()
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Inactive Ratio Analyzer", "serial_number": "STOCK-002"},
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Inactive Ratio Reagent",
            "unit": "L",
            "current_stock": 1.0,
            "alert_threshold": 0.2,
        },
    ).json()
    client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 0.9,
            "adjustment_factor": 1.0,
            "is_active": False,
        },
    )

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "equipment_id": equipment["id"],
            "data_points": {"WBC": 6.1},
            "is_critical": False,
        },
    )
    assert response.status_code == 201, response.text

    updated_reagent = client.get(
        f"/api/v1/reagents/{reagent['id']}", headers=headers
    ).json()
    assert updated_reagent["current_stock"] == 1.0


def test_insufficient_stock_blocks_result_validation(client) -> None:
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-STOCK-003",
            "first_name": "Low",
            "last_name": "Stock",
            "birth_date": "1991-01-10",
            "sex": "M",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "BAR-STOCK-003",
            "patient_id": patient["id"],
            "status": "Recu",
        },
    ).json()
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Low Stock Analyzer", "serial_number": "STOCK-003"},
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Low Stock Reagent",
            "unit": "L",
            "current_stock": 0.1,
            "alert_threshold": 0.2,
        },
    ).json()
    client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 0.2,
            "adjustment_factor": 1.0,
            "is_active": True,
        },
    )

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "equipment_id": equipment["id"],
            "data_points": {"WBC": 6.1},
            "is_critical": False,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["items"][0]["reagent_name"] == "Low Stock Reagent"

    results = client.get("/api/v1/results", headers=headers).json()
    assert all(item["sample_id"] != sample["id"] for item in results["items"])


def test_dh36_ingestion_creates_validated_result_and_is_idempotent(client) -> None:
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-DH36-001",
            "first_name": "Dymind",
            "last_name": "Runner",
            "birth_date": "1990-01-10",
            "sex": "M",
        },
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "BAR-DH36-001", "patient_id": patient["id"], "status": "Recu"},
    ).json()
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Dymind DH36",
            "serial_number": "DH36-ING-001",
            "type": "Automate",
        },
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "DH36 Ingest Diluant",
            "category": "hematology",
            "unit": "L",
            "current_stock": 1.0,
            "alert_threshold": 0.2,
        },
    ).json()
    client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": 0.25,
            "adjustment_factor": 1.0,
            "is_active": True,
        },
    )

    response = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={"raw_message": _dh36_message("BAR-DH36-001", "MSG-DH36-001")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "processed"
    result_id = response.json()["result_id"]

    result_response = client.get(f"/api/v1/results/{result_id}", headers=headers)
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["sample_id"] == sample["id"]
    assert result_payload["equipment_id"] == equipment["id"]
    assert result_payload["is_validated"] is True
    assert result_payload["data_points"]["WBC"]["status"] == "N"

    updated_reagent = client.get(
        f"/api/v1/reagents/{reagent['id']}", headers=headers
    ).json()
    assert updated_reagent["current_stock"] == 0.75

    duplicate_response = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={"raw_message": _dh36_message("BAR-DH36-001", "MSG-DH36-001")},
    )
    assert duplicate_response.status_code == 202
    assert duplicate_response.json()["status"] == "duplicate"
    assert duplicate_response.json()["result_id"] == result_id

    results = client.get(
        f"/api/v1/results?sample_id={sample['id']}", headers=headers
    ).json()
    assert results["meta"]["total"] == 1


def test_dh36_ingestion_rejects_unknown_barcode(client) -> None:
    headers = _auth_headers(client)
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Dymind DH36",
            "serial_number": "DH36-ING-001",
            "type": "Automate",
        },
    )

    response = client.post(
        "/api/v1/dh36/ingest",
        headers=headers,
        json={"raw_message": _dh36_message("BAR-UNKNOWN", "MSG-DH36-UNKNOWN")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["rejection_reason"] == "Code-barres inconnu: BAR-UNKNOWN."


def test_validate_order_is_audited(client) -> None:
    headers = _auth_headers(client)
    reagent_response = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Buffer FIA",
            "category": "immunology",
            "unit": "unit",
            "current_stock": 10.0,
            "alert_threshold": 2.0,
        },
    )
    reagent_id = reagent_response.json()["id"]

    response = client.post(
        "/api/v1/operations/validate-order",
        headers=headers,
        json={
            "reagent_id": reagent_id,
            "order_reference": "CMD-2026-001",
            "notes": "Urgent replenishment approved",
        },
    )
    assert response.status_code == 200
    assert response.json()["validated_by"] == "admin"

    audit_response = client.get("/api/v1/audit-events", headers=headers)
    assert any(
        event["event_type"] == "operation.validate_order"
        for event in audit_response.json()["items"]
    )

    activity_response = client.get("/api/v1/reports/audit-activity", headers=headers)
    assert activity_response.status_code == 200
    assert len(activity_response.json()["items"]) >= 1


def test_validate_order_rejects_unknown_reagent(client) -> None:
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/operations/validate-order",
        headers=headers,
        json={
            "reagent_id": 9999,
            "order_reference": "CMD-2026-404",
            "notes": "Should fail",
        },
    )
    assert response.status_code == 404


def test_imaging_endpoint_sanitizes_generated_image_path(client) -> None:
    headers = _auth_headers(client)
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": "IPP-920",
            "first_name": "Secure",
            "last_name": "Path",
            "birth_date": "1990-02-10",
            "sex": "M",
            "rank": "Lieutenant",
        },
    ).json()
    client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": "../evil\\path",
            "patient_id": patient["id"],
            "status": "Recu",
        },
    )
    client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Magnus Theia-i",
            "serial_number": "MAG-920",
            "type": "Microscope",
        },
    )

    response = client.post(
        "/api/v1/imaging/capture-microscope",
        headers=headers,
        json={"sample_barcode": "../evil\\path"},
    )
    assert response.status_code == 201, response.text
    image_url = response.json()["image_url"]
    assert ".." not in image_url
    assert "\\" not in image_url


def test_ratio_presets_and_versioning(client) -> None:
    headers = _auth_headers(client)
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Dymind DX5", "serial_number": "DX5-1", "type": "Automate"},
    ).json()
    preset = client.post(
        "/api/v1/ratio-presets",
        headers=headers,
        json={
            "name": "DX5 default preset",
            "equipment_name": "Dymind DX5",
            "description": "Preset de depart pour DX5",
            "is_active": True,
        },
    )
    assert preset.status_code == 201, preset.text
    preset_id = preset.json()["id"]
    item = client.post(
        "/api/v1/ratio-presets/items",
        headers=headers,
        json={
            "preset_id": preset_id,
            "reagent_name": "Cleaner DX5",
            "reagent_category": "hematology",
            "reagent_unit": "L",
            "consumption_per_run": 0.005,
            "adjustment_factor": 1.1,
            "notes": "Maintenance incluse",
            "is_active": True,
        },
    )
    assert item.status_code == 201, item.text

    apply_response = client.post(
        f"/api/v1/ratio-presets/{preset_id}/apply?equipment_id={equipment['id']}",
        headers=headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["applied_count"] == 1

    reagents = client.get("/api/v1/reagents", headers=headers).json()["items"]
    cleaner = next(item for item in reagents if item["name"] == "Cleaner DX5")
    ratios = client.get(
        f"/api/v1/equipment-reagent-ratios?equipment_id={equipment['id']}",
        headers=headers,
    )
    assert ratios.status_code == 200
    ratio = next(
        item for item in ratios.json()["items"] if item["reagent_id"] == cleaner["id"]
    )

    update_response = client.put(
        f"/api/v1/equipment-reagent-ratios/{ratio['id']}",
        headers=headers,
        json={"adjustment_factor": 1.2, "notes": "Ajuste apres observation"},
    )
    assert update_response.status_code == 200, update_response.text

    versions = client.get(
        f"/api/v1/equipment-reagent-ratios/{ratio['id']}/versions", headers=headers
    )
    assert versions.status_code == 200
    assert len(versions.json()) >= 2


def test_inactive_ratio_presets_and_items_are_not_applied(client) -> None:
    headers = _auth_headers(client)
    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": "Dymind DX5",
            "serial_number": "DX5-INACTIVE",
            "type": "Automate",
        },
    ).json()
    inactive_preset = client.post(
        "/api/v1/ratio-presets",
        headers=headers,
        json={
            "name": "Inactive preset",
            "equipment_name": "Dymind DX5",
            "is_active": False,
        },
    ).json()

    inactive_apply = client.post(
        f"/api/v1/ratio-presets/{inactive_preset['id']}/apply?equipment_id={equipment['id']}",
        headers=headers,
    )
    assert inactive_apply.status_code == 409

    active_preset = client.post(
        "/api/v1/ratio-presets",
        headers=headers,
        json={
            "name": "Preset with inactive item",
            "equipment_name": "Dymind DX5",
            "is_active": True,
        },
    ).json()
    client.post(
        "/api/v1/ratio-presets/items",
        headers=headers,
        json={
            "preset_id": active_preset["id"],
            "reagent_name": "Inactive Cleaner",
            "consumption_per_run": 0.005,
            "is_active": False,
        },
    )

    apply_response = client.post(
        f"/api/v1/ratio-presets/{active_preset['id']}/apply?equipment_id={equipment['id']}",
        headers=headers,
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["applied_count"] == 0
    reagents = client.get("/api/v1/reagents", headers=headers).json()["items"]
    assert all(item["name"] != "Inactive Cleaner" for item in reagents)


def test_negative_stock_and_ratio_values_are_rejected(client) -> None:
    headers = _auth_headers(client)
    reagent_response = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={
            "name": "Invalid Stock",
            "current_stock": -1.0,
            "alert_threshold": 0.0,
        },
    )
    assert reagent_response.status_code == 422

    equipment = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={"name": "Ratio Guard", "serial_number": "RG-1"},
    ).json()
    reagent = client.post(
        "/api/v1/reagents",
        headers=headers,
        json={"name": "Valid Stock", "current_stock": 1.0, "alert_threshold": 0.0},
    ).json()
    ratio_response = client.post(
        "/api/v1/equipment-reagent-ratios",
        headers=headers,
        json={
            "equipment_id": equipment["id"],
            "reagent_id": reagent["id"],
            "consumption_per_run": -0.1,
            "adjustment_factor": 1.0,
        },
    )
    assert ratio_response.status_code == 422

    preset_item_response = client.post(
        "/api/v1/ratio-presets/items",
        headers=headers,
        json={
            "preset_id": 1,
            "reagent_name": "Bad Preset",
            "consumption_per_run": 0.1,
            "adjustment_factor": 0,
        },
    )
    assert preset_item_response.status_code == 422

"""Prescription → machine compatible → formulaire → interprétation."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup(
    client, exams: list[str], *, collect: bool = True
) -> tuple[dict, dict, dict, dict[str, str]]:
    headers = _auth(client)
    client.post("/api/v1/bioref/seed-defaults", headers=headers)
    client.post("/api/v1/code-mappings/seed-defaults", headers=headers)
    suffix = uuid.uuid4().hex[:8]
    patient = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"ENTRY-{suffix}",
            "first_name": "Awa",
            "last_name": "Entry",
            "birth_date": "1990-01-01",
            "sex": "F",
        },
    ).json()
    order = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={"patient_id": patient["id"], "exams": [{"exam_code": code} for code in exams]},
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": f"ENTRY-{suffix}",
            "patient_id": patient["id"],
            "status": "Recu",
        },
    ).json()
    if collect:
        response = client.post(
            f"/api/v1/exam-orders/{order['id']}/collect",
            headers=headers,
            json={"sample_id": sample["id"]},
        )
        assert response.status_code == 200, response.text
    return patient, order, sample, headers


def _equipment(client, headers, name: str, equipment_type: str) -> dict:
    return client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": name,
            "serial_number": f"{name}-{uuid.uuid4().hex[:8]}",
            "type": equipment_type,
        },
    ).json()


def test_entry_context_loads_prescribed_exams_and_compatible_machines(client) -> None:
    _, _, sample, headers = _setup(client, ["NFS", "GLYC"])
    dh36 = _equipment(client, headers, "Dymind DH36", "Hématologie")
    precis = _equipment(client, headers, "Precis Expert", "POCT")

    response = client.get(
        f"/api/v1/results/entry-context/{sample['id']}", headers=headers
    )

    assert response.status_code == 200, response.text
    exams = {item["exam_code"]: item for item in response.json()["exams"]}
    assert set(exams) == {"NFS", "GLYC"}
    assert dh36["id"] in exams["NFS"]["compatible_equipment_ids"]
    assert precis["id"] not in exams["NFS"]["compatible_equipment_ids"]
    assert precis["id"] in exams["GLYC"]["compatible_equipment_ids"]
    nfs_fields = {field["key"]: field for field in exams["NFS"]["fields"]}
    assert nfs_fields["HGB"]["unit"] == "g/dL"
    assert nfs_fields["WBC"]["unit"] == "10*9/L"


def test_single_open_prescription_is_linked_when_sample_is_created(client) -> None:
    _, order, sample, headers = _setup(client, ["NFS"], collect=False)
    thread = client.get(f"/api/v1/exam-orders/{order['id']}/thread", headers=headers)
    assert thread.status_code == 200
    assert thread.json()["sample_id"] == sample["id"]
    assert thread.json()["status"] == "collected"


def test_result_rejects_machine_incompatible_with_prescribed_exam(client) -> None:
    _, _, sample, headers = _setup(client, ["NFS"])
    precis = _equipment(client, headers, "Precis Expert", "POCT")

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "equipment_id": precis["id"],
            "exam_code": "NFS",
            "data_points": {"HGB": {"value": 8, "unit": "g/dL"}},
        },
    )

    assert response.status_code == 422
    assert "n'est pas configuré" in response.json()["detail"]


def test_result_rejects_analyte_not_belonging_to_prescription(client) -> None:
    _, _, sample, headers = _setup(client, ["GLYC"])

    response = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "exam_code": "GLYC",
            "data_points": {"HGB": {"value": 8, "unit": "g/dL"}},
        },
    )

    assert response.status_code == 422
    assert "incompatible" in response.json()["detail"]


def test_hgb_low_is_flagged_and_critical_threshold_converts_units(client) -> None:
    _, order, sample, headers = _setup(client, ["NFS"])
    low = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "exam_code": "NFS",
            "data_points": {"HGB": {"value": 8, "unit": "g/dL"}},
        },
    )
    assert low.status_code == 201, low.text
    assert low.json()["flags"]["HB"] == "BAS"
    assert low.json()["data_points"]["HGB"]["status"] == "L"
    assert low.json()["is_critical"] is False
    thread = client.get(f"/api/v1/exam-orders/{order['id']}/thread", headers=headers).json()
    assert thread["status"] == "completed"

    # Nouveau patient/bon : 70 g/L = 7 g/dL, seuil critique inclusif.
    _, _, critical_sample, critical_headers = _setup(client, ["NFS"])
    critical = client.post(
        "/api/v1/results",
        headers=critical_headers,
        json={
            "sample_id": critical_sample["id"],
            "exam_code": "NFS",
            "data_points": {"HGB": {"value": 70, "unit": "g/L"}},
        },
    )
    assert critical.status_code == 201, critical.text
    assert critical.json()["is_critical"] is True
    assert critical.json()["data_points"]["HGB"]["status"] == "LL"

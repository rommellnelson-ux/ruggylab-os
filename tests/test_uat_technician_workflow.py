"""Scénarios automatisés du protocole terrain techniciens.

Ces tests sécurisent les règles déterministes. Ils ne remplacent pas
l'observation d'utilisateurs réels décrite dans docs/UAT_TECHNICIENS.md.
"""

from __future__ import annotations

import json
import uuid


def _auth(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _patient(client, headers: dict[str, str], *, sex: str = "F") -> dict:
    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": f"UAT-{suffix}",
            "first_name": "UAT",
            "last_name": f"Technicien-{suffix}",
            "birth_date": "1990-01-01",
            "sex": sex,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _order_and_sample(
    client,
    headers: dict[str, str],
    *,
    exams: list[str],
    aspect: str = "conforme",
) -> tuple[dict, dict, dict]:
    patient = _patient(client, headers)
    order_response = client.post(
        "/api/v1/exam-orders",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "prescriber": "Dr UAT",
            "priority": "routine",
            "exams": [{"exam_code": code} for code in exams],
        },
    )
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()
    sample_response = client.post(
        "/api/v1/samples",
        headers=headers,
        json={
            "barcode": f"UAT-{uuid.uuid4().hex[:10]}",
            "patient_id": patient["id"],
            "status": "Recu",
            "aspect": aspect,
        },
    )
    assert sample_response.status_code == 201, sample_response.text
    return patient, order, sample_response.json()


def _equipment(client, headers: dict[str, str], *, name: str, kind: str) -> dict:
    response = client.post(
        "/api/v1/equipments",
        headers=headers,
        json={
            "name": name,
            "serial_number": f"UAT-{uuid.uuid4().hex[:10]}",
            "type": kind,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_references(client, headers: dict[str, str]) -> None:
    assert client.post("/api/v1/bioref/seed-defaults", headers=headers).status_code == 200
    assert client.post("/api/v1/code-mappings/seed-defaults", headers=headers).status_code == 200


def test_uat_patient_prescription_sample_and_machine_selection(client) -> None:
    """UAT-T01/T02/T04 : prescription et appareils restent cohérents."""
    headers = _auth(client)
    _seed_references(client, headers)
    patient, order, sample = _order_and_sample(
        client, headers, exams=["NFS", "GLYC"]
    )
    dh36 = _equipment(client, headers, name="Dymind DH36", kind="Hématologie")
    precis = _equipment(client, headers, name="Precis Expert", kind="POCT")

    lookup = client.get(
        f"/api/v1/samples/by-barcode/{sample['barcode']}", headers=headers
    )
    assert lookup.status_code == 200
    assert lookup.json()["patient_id"] == patient["id"]

    thread = client.get(f"/api/v1/exam-orders/{order['id']}/thread", headers=headers)
    assert thread.status_code == 200
    assert thread.json()["sample_id"] == sample["id"]

    context = client.get(
        f"/api/v1/results/entry-context/{sample['id']}", headers=headers
    )
    assert context.status_code == 200, context.text
    exams = {item["exam_code"]: item for item in context.json()["exams"]}
    assert set(exams) == {"NFS", "GLYC"}
    assert dh36["id"] in exams["NFS"]["compatible_equipment_ids"]
    assert precis["id"] not in exams["NFS"]["compatible_equipment_ids"]
    assert precis["id"] in exams["GLYC"]["compatible_equipment_ids"]

    incompatible = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "exam_code": "NFS",
            "equipment_id": precis["id"],
            "data_points": {"HGB": {"value": 12.5, "unit": "g/dL"}},
        },
    )
    assert incompatible.status_code == 422


def test_uat_nonconforming_sample_is_traceable_in_quality_summary(client) -> None:
    """UAT-T03 : un tube hémolysé annulé reste comptabilisé."""
    headers = _auth(client)
    _, _, sample = _order_and_sample(
        client, headers, exams=["GLYC"], aspect="hemolyse"
    )

    cancelled = client.patch(
        f"/api/v1/samples/{sample['id']}",
        headers=headers,
        json={"status": "Annule"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "Annule"
    assert cancelled.json()["aspect"] == "hemolyse"

    summary = client.get("/api/v1/samples/quality-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["by_aspect"]["hemolyse"] >= 1
    assert summary.json()["non_conformity_rate_pct"] > 0


def test_uat_normal_abnormal_and_critical_results(client) -> None:
    """UAT-T05/T06/T07 : les trois niveaux sont distingués."""
    headers = _auth(client)
    _seed_references(client, headers)

    expected = [
        (13.0, "N", False),
        (8.0, "L", False),
        (7.0, "LL", True),
    ]
    for value, status, is_critical in expected:
        _, _, sample = _order_and_sample(client, headers, exams=["NFS"])
        response = client.post(
            "/api/v1/results",
            headers=headers,
            json={
                "sample_id": sample["id"],
                "exam_code": "NFS",
                "data_points": {"HGB": {"value": value, "unit": "g/dL"}},
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["data_points"]["HGB"]["status"] == status
        assert payload["is_critical"] is is_critical


def test_uat_result_correction_is_visible_and_audited(client) -> None:
    """UAT-T08 : la correction exige un motif et génère une trace."""
    headers = _auth(client)
    _seed_references(client, headers)
    _, _, sample = _order_and_sample(client, headers, exams=["NFS"])
    created = client.post(
        "/api/v1/results",
        headers=headers,
        json={
            "sample_id": sample["id"],
            "exam_code": "NFS",
            "data_points": {"HGB": {"value": 8, "unit": "g/dL"}},
        },
    )
    assert created.status_code == 201, created.text
    result_id = created.json()["id"]

    amended = client.patch(
        f"/api/v1/results/{result_id}/amend",
        headers=headers,
        json={
            "data_points": {"HGB": {"value": 9, "unit": "g/dL"}},
            "amendment_reason": "Contrôle UAT — répétition analytique",
        },
    )
    assert amended.status_code == 200, amended.text
    assert amended.json()["data_points"]["HGB"]["value"] == 9
    assert amended.json()["amendment_reason"] == "Contrôle UAT — répétition analytique"

    audit = client.get(
        f"/api/v1/results/{result_id}/clinical-audit", headers=headers
    )
    assert audit.status_code == 200
    events = audit.json()
    assert any(event["event_type"] == "result.amend" for event in events)
    amendment_event = next(
        event for event in events if event["event_type"] == "result.amend"
    )
    audit_payload = json.loads(amendment_event["payload"])
    assert audit_payload["amendment_reason"] == "Contrôle UAT — répétition analytique"

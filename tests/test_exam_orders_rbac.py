"""Tests — cloisonnement RBAC par unité des prescriptions d'examens (F2).

Aligne exam-orders sur results/patients : un technicien rattaché à une unité
n'accède qu'aux prescriptions des patients de son unité (ou sans unité).
"""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _tech(client, admin, *, unit: str | None) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    body = {"username": f"t_{u}", "password": "TechPass123!", "role": "technician"}
    if unit is not None:
        body["unit"] = unit
    client.post("/api/v1/users", headers=admin, json=body)
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"t_{u}", "password": "TechPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _order(client, admin, *, unit: str | None) -> int:
    body = {
        "ipp_unique_id": f"EO-{uuid.uuid4().hex[:8]}",
        "first_name": "Eo",
        "last_name": "Test",
        "birth_date": "1980-01-01",
        "sex": "M",
    }
    if unit is not None:
        body["unit"] = unit
    pid = client.post("/api/v1/patients", headers=admin, json=body).json()["id"]
    return client.post(
        "/api/v1/exam-orders",
        headers=admin,
        json={"patient_id": pid, "exams": [{"exam_code": "NFS"}]},
    ).json()["id"]


class TestExamOrderUnitScope:
    def test_list_excludes_other_unit(self, client):
        admin = _auth(client)
        oid_bio = _order(client, admin, unit="biochimie")
        oid_hema = _order(client, admin, unit="hematologie")
        tech = _tech(client, admin, unit="hematologie")
        ids = {o["id"] for o in client.get("/api/v1/exam-orders", headers=tech).json()}
        assert oid_hema in ids
        assert oid_bio not in ids

    def test_detail_and_thread_denied_other_unit(self, client):
        admin = _auth(client)
        oid = _order(client, admin, unit="biochimie")
        tech = _tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/exam-orders/{oid}", headers=tech).status_code == 403
        assert client.get(f"/api/v1/exam-orders/{oid}/thread", headers=tech).status_code == 403
        assert client.post(f"/api/v1/exam-orders/{oid}/invoice", headers=tech).status_code == 403

    def test_same_unit_allowed(self, client):
        admin = _auth(client)
        oid = _order(client, admin, unit="hematologie")
        tech = _tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/exam-orders/{oid}", headers=tech).status_code == 200

    def test_unaffiliated_patient_visible(self, client):
        admin = _auth(client)
        oid = _order(client, admin, unit=None)  # patient sans unité = pool partagé
        tech = _tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/exam-orders/{oid}", headers=tech).status_code == 200

    def test_cannot_create_order_for_other_unit_patient(self, client):
        admin = _auth(client)
        pid = client.post(
            "/api/v1/patients",
            headers=admin,
            json={
                "ipp_unique_id": f"EO-{uuid.uuid4().hex[:8]}",
                "first_name": "X",
                "last_name": "Y",
                "birth_date": "1980-01-01",
                "sex": "M",
                "unit": "biochimie",
            },
        ).json()["id"]
        tech = _tech(client, admin, unit="hematologie")
        r = client.post(
            "/api/v1/exam-orders",
            headers=tech,
            json={"patient_id": pid, "exams": [{"exam_code": "NFS"}]},
        )
        assert r.status_code == 403

    def test_admin_sees_all(self, client):
        admin = _auth(client)
        oid_bio = _order(client, admin, unit="biochimie")
        assert client.get(f"/api/v1/exam-orders/{oid_bio}", headers=admin).status_code == 200


class TestConsolidatedReport:
    def test_report_pdf_consolidates_results(self, client):
        admin = _auth(client)
        pid = client.post(
            "/api/v1/patients",
            headers=admin,
            json={
                "ipp_unique_id": f"RPT-{uuid.uuid4().hex[:8]}",
                "first_name": "Cr",
                "last_name": "Test",
                "birth_date": "1980-01-01",
                "sex": "F",
            },
        ).json()["id"]
        oid = client.post(
            "/api/v1/exam-orders",
            headers=admin,
            json={"patient_id": pid, "exams": [{"exam_code": "NFS"}, {"exam_code": "GE"}]},
        ).json()["id"]
        barcode = f"RPT-{uuid.uuid4().hex[:10]}"
        sid = client.post(
            "/api/v1/samples",
            headers=admin,
            json={"barcode": barcode, "patient_id": pid, "status": "Recu"},
        ).json()["id"]
        client.post(f"/api/v1/exam-orders/{oid}/collect", headers=admin, json={"barcode": barcode})
        client.post(
            "/api/v1/results",
            headers=admin,
            json={"sample_id": sid, "exam_code": "NFS", "data_points": {"WBC": 5.0}},
        )
        r = client.get(f"/api/v1/exam-orders/{oid}/report.pdf", headers=admin)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"

    def test_report_denied_other_unit(self, client):
        admin = _auth(client)
        oid = _order(client, admin, unit="biochimie")
        tech = _tech(client, admin, unit="hematologie")
        assert client.get(f"/api/v1/exam-orders/{oid}/report.pdf", headers=tech).status_code == 403

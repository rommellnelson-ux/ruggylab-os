"""Tests — Prescription d'examens et suivi du fil (prescription → résultat)."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_patient(client, hdrs) -> int:
    return client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"EO-{uuid.uuid4().hex[:8]}",
            "first_name": "Exam",
            "last_name": "Order",
            "birth_date": "1990-01-01",
            "sex": "M",
        },
    ).json()["id"]


def _make_sample(client, hdrs, patient_id) -> dict:
    return client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"EO-{uuid.uuid4().hex[:10]}", "patient_id": patient_id, "status": "Recu"},
    ).json()


def _accountant(client, admin) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"compta_{u}", "password": "ComptaPass123!", "role": "accountant"},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"compta_{u}", "password": "ComptaPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


class TestExamOrderLifecycle:
    def test_create_order_prescribed(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        r = client.post(
            "/api/v1/exam-orders",
            headers=hdrs,
            json={
                "patient_id": pid,
                "prescriber": "Dr Koffi",
                "priority": "urgent",
                "exams": [
                    {"exam_code": "NFS"},
                    {"exam_code": "GE", "exam_label": "Goutte épaisse"},
                ],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "prescribed"
        assert len(body["items"]) == 2
        assert {i["status"] for i in body["items"]} == {"pending"}

    def test_thread_follows_result(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        order = client.post(
            "/api/v1/exam-orders",
            headers=hdrs,
            json={"patient_id": pid, "exams": [{"exam_code": "NFS"}, {"exam_code": "GE"}]},
        ).json()
        oid = order["id"]

        # 1) prélèvement : on rattache l'échantillon par code-barres
        sample = _make_sample(client, hdrs, pid)
        thread = client.post(
            f"/api/v1/exam-orders/{oid}/collect",
            headers=hdrs,
            json={"barcode": sample["barcode"]},
        ).json()
        assert thread["status"] == "collected"
        assert thread["sample_barcode"] == sample["barcode"]
        assert thread["progress_pct"] == 0

        # 2) un résultat NFS remonte → l'examen passe à resulted, fil en cours
        client.post(
            "/api/v1/results",
            headers=hdrs,
            json={"sample_id": sample["id"], "exam_code": "NFS", "data_points": {"WBC": 5.0}},
        )
        thread = client.get(f"/api/v1/exam-orders/{oid}/thread", headers=hdrs).json()
        assert thread["resulted_exams"] == 1
        assert thread["status"] == "in_progress"
        assert thread["progress_pct"] == 50
        nfs = next(s for s in thread["steps"] if s["exam_code"] == "NFS")
        assert nfs["status"] == "resulted"
        assert nfs["result_id"] is not None
        assert nfs["preanalytics"]["container"] == "Tube EDTA violet"
        assert nfs["technical_sheet"]["key_steps"]
        ge = next(s for s in thread["steps"] if s["exam_code"] == "GE")
        assert ge["preanalytics"]["bench"] == "Parasitologie"

        # 3) le second résultat → fil complété
        client.post(
            "/api/v1/results",
            headers=hdrs,
            json={"sample_id": sample["id"], "exam_code": "GE", "data_points": {"GE": 0}},
        )
        thread = client.get(f"/api/v1/exam-orders/{oid}/thread", headers=hdrs).json()
        assert thread["status"] == "completed"
        assert thread["progress_pct"] == 100

    def test_cancel_order(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        oid = client.post(
            "/api/v1/exam-orders",
            headers=hdrs,
            json={"patient_id": pid, "exams": [{"exam_code": "CRP"}]},
        ).json()["id"]
        r = client.patch(f"/api/v1/exam-orders/{oid}", headers=hdrs, json={"status": "cancelled"})
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_list_filter_by_patient(self, client):
        hdrs = _auth(client)
        pid = _make_patient(client, hdrs)
        client.post(
            "/api/v1/exam-orders",
            headers=hdrs,
            json={"patient_id": pid, "exams": [{"exam_code": "NFS"}]},
        )
        rows = client.get(f"/api/v1/exam-orders?patient_id={pid}", headers=hdrs).json()
        assert len(rows) == 1
        assert rows[0]["patient_id"] == pid


class TestExamOrderRbac:
    def test_unknown_patient_404(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/exam-orders",
            headers=hdrs,
            json={"patient_id": 999999, "exams": [{"exam_code": "NFS"}]},
        )
        assert r.status_code == 404

    def test_accountant_denied(self, client):
        admin = _auth(client)
        compta = _accountant(client, admin)
        assert client.get("/api/v1/exam-orders", headers=compta).status_code == 403

    def test_requires_auth(self, client):
        assert client.get("/api/v1/exam-orders").status_code == 401

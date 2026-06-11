"""Tests — Filtres audit, export CSV, et synthèse de conformité ISO 15189."""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _make_patient_sample_result(client, hdrs) -> int:
    pid = client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"AC-{_uid()}",
            "first_name": "Audit",
            "last_name": "Compliance",
            "birth_date": "1980-01-01",
            "sex": "M",
        },
    ).json()["id"]
    sid = client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"AC-{_uid()}", "patient_id": pid, "status": "Recu"},
    ).json()["id"]
    r = client.post(
        "/api/v1/results",
        headers=hdrs,
        json={"sample_id": sid, "data_points": {"WBC": 5.0}, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestAuditFilters:
    def test_filter_by_event_type(self, client):
        hdrs = _auth(client)
        # Create a reagent → reagent.create audit event
        client.post(
            "/api/v1/reagents",
            headers=hdrs,
            json={"name": f"Rg-{_uid()}", "unit": "unit", "current_stock": 1, "alert_threshold": 0},
        )
        r = client.get("/api/v1/audit-events?event_type=reagent.create", headers=hdrs)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(e["event_type"] == "reagent.create" for e in items)
        assert len(items) >= 1

    def test_filter_unknown_user_returns_empty(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/audit-events?username=nonexistent_user_xyz", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_audit_requires_admin(self, client):
        # Create non-admin user
        hdrs = _auth(client)
        uid = _uid()
        client.post(
            "/api/v1/users",
            headers=hdrs,
            json={"username": f"tech_{uid}", "password": "TechPass123!", "role": "technician"},
        )
        tok = (
            client.post(
                "/api/v1/login/access-token",
                data={"username": f"tech_{uid}", "password": "TechPass123!"},
            )
            .json()
            .get("access_token")
        )
        if tok:
            r = client.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 403


class TestAuditCsvExport:
    def test_export_csv_returns_csv(self, client):
        hdrs = _auth(client)
        client.post(
            "/api/v1/reagents",
            headers=hdrs,
            json={"name": f"Rg-{_uid()}", "unit": "unit", "current_stock": 1, "alert_threshold": 0},
        )
        r = client.get("/api/v1/audit-events/export.csv", headers=hdrs)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        body = r.text
        assert "id,created_at,username,event_type" in body.splitlines()[0]

    def test_export_csv_requires_admin(self, client):
        hdrs = _auth(client)
        uid = _uid()
        client.post(
            "/api/v1/users",
            headers=hdrs,
            json={"username": f"tech_{uid}", "password": "TechPass123!", "role": "technician"},
        )
        tok = (
            client.post(
                "/api/v1/login/access-token",
                data={"username": f"tech_{uid}", "password": "TechPass123!"},
            )
            .json()
            .get("access_token")
        )
        if tok:
            r = client.get(
                "/api/v1/audit-events/export.csv", headers={"Authorization": f"Bearer {tok}"}
            )
            assert r.status_code == 403


class TestComplianceSummary:
    def test_compliance_summary_fields(self, client):
        hdrs = _auth(client)
        _make_patient_sample_result(client, hdrs)
        r = client.get("/api/v1/reports/compliance-summary?days=30", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        for field in (
            "total_results",
            "validated_results",
            "auto_validated_results",
            "critical_total",
            "critical_acked",
            "pending_criticals",
            "amendments",
            "signed_reports",
            "validation_rate_pct",
            "critical_ack_rate_pct",
            "auto_validation_rate_pct",
            "status",
        ):
            assert field in data, f"Champ manquant: {field}"
        assert data["status"] in ("compliant", "attention")
        assert data["total_results"] >= 1

    def test_compliance_counts_amendment(self, client):
        hdrs = _auth(client)
        result_id = _make_patient_sample_result(client, hdrs)
        client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 6.0}, "amendment_reason": "Correction test conformité"},
        )
        r = client.get("/api/v1/reports/compliance-summary?days=30", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["amendments"] >= 1

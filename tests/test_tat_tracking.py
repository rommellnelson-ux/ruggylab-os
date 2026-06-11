"""Tests — Suivi du TAT (Turnaround Time)."""
from __future__ import annotations

import datetime as dt
import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_result(client, hdrs, *, exam_code: str | None = None, data=None) -> dict:
    pid = client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={"ipp_unique_id": f"TT-{_uid()}", "first_name": "Tat", "last_name": "Test",
              "birth_date": "1980-01-01", "sex": "M"},
    ).json()["id"]
    sid = client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"TT-{_uid()}", "patient_id": pid, "status": "Recu"},
    ).json()["id"]
    body = {"sample_id": sid, "data_points": data or {"WBC": 5.0}, "is_critical": False}
    if exam_code:
        body["exam_code"] = exam_code
    r = client.post("/api/v1/results", headers=hdrs, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── Cibles TAT ──────────────────────────────────────────────────────────────

class TestTatTargets:
    def test_create_and_list(self, client):
        hdrs = _auth(client)
        code = f"EX{_uid()[:4].upper()}"
        r = client.post(
            "/api/v1/tat/targets",
            headers=hdrs,
            json={"exam_code": code, "label": "Examen test", "target_minutes": 60},
        )
        assert r.status_code == 201, r.text
        assert r.json()["target_minutes"] == 60
        assert r.json()["warn_factor"] == 1.5
        listed = client.get("/api/v1/tat/targets", headers=hdrs).json()
        assert any(t["exam_code"] == code for t in listed)

    def test_duplicate_active_rejected(self, client):
        hdrs = _auth(client)
        code = f"EX{_uid()[:4].upper()}"
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": code, "label": "X", "target_minutes": 30})
        r = client.post("/api/v1/tat/targets", headers=hdrs,
                        json={"exam_code": code, "label": "X", "target_minutes": 30})
        assert r.status_code == 409

    def test_deactivate(self, client):
        hdrs = _auth(client)
        code = f"EX{_uid()[:4].upper()}"
        tid = client.post("/api/v1/tat/targets", headers=hdrs,
                          json={"exam_code": code, "label": "X", "target_minutes": 30}).json()["id"]
        assert client.delete(f"/api/v1/tat/targets/{tid}", headers=hdrs).status_code == 200
        listed = client.get("/api/v1/tat/targets", headers=hdrs).json()
        assert all(t["id"] != tid for t in listed)

    def test_create_requires_officer(self, client):
        admin = _auth(client)
        u = _uid()
        client.post("/api/v1/users", headers=admin,
                    json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"})
        tok = client.post("/api/v1/login/access-token",
                          data={"username": f"tech_{u}", "password": "TechPass123!"}).json().get("access_token")
        if tok:
            r = client.post("/api/v1/tat/targets", headers={"Authorization": f"Bearer {tok}"},
                            json={"exam_code": "X", "label": "X", "target_minutes": 30})
            assert r.status_code == 403

    def test_seed_defaults(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/tat/targets/seed-defaults", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["created"] >= 1
        codes = {t["exam_code"] for t in client.get("/api/v1/tat/targets", headers=hdrs).json()}
        assert {"NFS", "GLYC", "CREAT", "GE", "ECBU"} <= codes
        # Idempotent : un second appel ne recrée rien
        assert client.post("/api/v1/tat/targets/seed-defaults", headers=hdrs).json()["created"] == 0


# ── Auto-population + calcul TAT ────────────────────────────────────────────

class TestResultTatAutoFill:
    def test_creation_sets_tat_timestamps(self, client):
        hdrs = _auth(client)
        r = _make_result(client, hdrs, exam_code="NFS")
        assert r["exam_code"] == "NFS"
        assert r["bio_validated_at"] is not None
        assert r["registered_at"] is not None

    def test_get_result_tat_phases(self, client):
        hdrs = _auth(client)
        r = _make_result(client, hdrs, exam_code="NFS")
        tat = client.get(f"/api/v1/tat/results/{r['id']}", headers=hdrs).json()
        assert tat["result_id"] == r["id"]
        assert "total_minutes" in tat
        assert "status" in tat


class TestResultTatUpdateAndStatus:
    def test_update_timestamps_and_status_green(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": "RAPID", "label": "Rapide", "target_minutes": 60})
        r = _make_result(client, hdrs, exam_code="RAPID")
        base = dt.datetime(2026, 1, 1, 8, 0, 0)
        upd = client.patch(
            f"/api/v1/tat/results/{r['id']}",
            headers=hdrs,
            json={
                "registered_at": base.isoformat(),
                "bio_validated_at": (base + dt.timedelta(minutes=30)).isoformat(),
            },
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()
        assert body["total_minutes"] == 30.0
        assert body["status"] == "green"
        assert body["is_late"] is False

    def test_status_orange_then_red(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": "SLOW", "label": "Lent", "target_minutes": 60, "warn_factor": 1.5})
        r = _make_result(client, hdrs, exam_code="SLOW")
        base = dt.datetime(2026, 1, 1, 8, 0, 0)
        # 80 min → entre 60 et 90 → orange
        orange = client.patch(f"/api/v1/tat/results/{r['id']}", headers=hdrs, json={
            "registered_at": base.isoformat(),
            "bio_validated_at": (base + dt.timedelta(minutes=80)).isoformat(),
        }).json()
        assert orange["status"] == "orange"
        # 200 min → > 90 → rouge
        red = client.patch(f"/api/v1/tat/results/{r['id']}", headers=hdrs, json={
            "bio_validated_at": (base + dt.timedelta(minutes=200)).isoformat(),
        }).json()
        assert red["status"] == "red"

    def test_phase_breakdown(self, client):
        hdrs = _auth(client)
        r = _make_result(client, hdrs, exam_code="NFS")
        base = dt.datetime(2026, 1, 1, 8, 0, 0)
        body = client.patch(f"/api/v1/tat/results/{r['id']}", headers=hdrs, json={
            "prescribed_at": base.isoformat(),
            "received_at": (base + dt.timedelta(minutes=20)).isoformat(),
            "analysis_started_at": (base + dt.timedelta(minutes=25)).isoformat(),
            "analysis_finished_at": (base + dt.timedelta(minutes=40)).isoformat(),
            "bio_validated_at": (base + dt.timedelta(minutes=50)).isoformat(),
        }).json()
        assert body["pre_analytic_minutes"] == 20.0     # received - prescribed
        assert body["analytic_minutes"] == 15.0          # finished - started
        assert body["post_analytic_minutes"] == 10.0     # bio_validated - finished

    def test_update_nonexistent(self, client):
        hdrs = _auth(client)
        r = client.patch("/api/v1/tat/results/999999", headers=hdrs, json={"exam_code": "X"})
        assert r.status_code == 404


# ── Tableau de bord & alertes ───────────────────────────────────────────────

class TestTatDashboard:
    def test_dashboard_structure(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": "NFS", "label": "NFS", "target_minutes": 60})
        _make_result(client, hdrs, exam_code="NFS")
        d = client.get("/api/v1/tat/dashboard?days=30", headers=hdrs).json()
        for key in ("total_measured", "late_count", "on_time_pct", "by_exam",
                    "by_technician", "by_automate", "by_day"):
            assert key in d
        assert d["total_measured"] >= 1

    def test_dashboard_late_detection(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": "FAST", "label": "Fast", "target_minutes": 10})
        r = _make_result(client, hdrs, exam_code="FAST")
        base = dt.datetime(2026, 1, 1, 8, 0, 0)
        # 120 min ≫ 10 → retard
        client.patch(f"/api/v1/tat/results/{r['id']}", headers=hdrs, json={
            "registered_at": base.isoformat(),
            "bio_validated_at": (base + dt.timedelta(minutes=120)).isoformat(),
        })
        # bio_validated_at est en 2026-01-01 → hors fenêtre 30j ; on élargit
        d = client.get("/api/v1/tat/dashboard?days=366", headers=hdrs).json()
        exam = next((e for e in d["by_exam"] if e["exam_code"] == "FAST"), None)
        assert exam is not None
        assert exam["late_count"] >= 1

    def test_alerts_endpoint(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/tat/targets", headers=hdrs,
                    json={"exam_code": "AL", "label": "Alert", "target_minutes": 5})
        r = _make_result(client, hdrs, exam_code="AL")
        now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        client.patch(f"/api/v1/tat/results/{r['id']}", headers=hdrs, json={
            "registered_at": (now - dt.timedelta(hours=2)).isoformat(),
            "bio_validated_at": now.isoformat(),
        })
        alerts = client.get("/api/v1/tat/alerts?days=7", headers=hdrs).json()
        assert any(a["result_id"] == r["id"] for a in alerts)

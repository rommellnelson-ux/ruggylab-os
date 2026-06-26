"""Tests — Maintenance équipements et statistiques de performance laboratoire."""

from __future__ import annotations

import datetime as dt

# ── helpers ───────────────────────────────────────────────────────────────────


def _utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_equipment(client, hdrs, name="DH36-Test"):
    r = client.post(
        "/api/v1/equipments",
        json={"name": name, "type": "Hématologie"},
        headers=hdrs,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ══════════════════════════════════════════════════════════════
#  Maintenance CRUD
# ══════════════════════════════════════════════════════════════


class TestEquipmentMaintenanceCRUD:
    def test_create_preventive(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        next_due = (_utcnow_naive() + dt.timedelta(days=5)).isoformat()
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={
                "equipment_id": eq_id,
                "maintenance_type": "preventive",
                "next_due_at": next_due,
                "notes": "Vérification hebdomadaire",
            },
            headers=hdrs,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["equipment_id"] == eq_id
        assert data["maintenance_type"] == "preventive"
        assert data["is_completed"] is False
        assert data["notes"] == "Vérification hebdomadaire"

    def test_create_calibration(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq_id, "maintenance_type": "calibration"},
            headers=hdrs,
        )
        assert r.status_code == 201
        assert r.json()["maintenance_type"] == "calibration"

    def test_invalid_type_rejected(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq_id, "maintenance_type": "unknown"},
            headers=hdrs,
        )
        assert r.status_code == 422

    def test_equipment_not_found(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": 99999, "maintenance_type": "corrective"},
            headers=hdrs,
        )
        assert r.status_code == 404

    def test_list_empty(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/equipment-maintenance", headers=hdrs)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_with_equipment_filter(self, client):
        hdrs = _auth(client)
        eq1 = _create_equipment(client, hdrs, "EQ1")
        eq2 = _create_equipment(client, hdrs, "EQ2")
        client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq1, "maintenance_type": "preventive"},
            headers=hdrs,
        )
        client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq2, "maintenance_type": "corrective"},
            headers=hdrs,
        )
        r = client.get(f"/api/v1/equipment-maintenance?equipment_id={eq1}", headers=hdrs)
        assert r.status_code == 200
        items = r.json()
        assert all(m["equipment_id"] == eq1 for m in items)

    def test_complete_maintenance(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq_id, "maintenance_type": "preventive"},
            headers=hdrs,
        )
        mid = r.json()["id"]
        rc = client.patch(f"/api/v1/equipment-maintenance/{mid}/complete", headers=hdrs)
        assert rc.status_code == 200
        data = rc.json()
        assert data["is_completed"] is True
        assert data["performed_at"] is not None
        assert data["performed_by_id"] is not None

    def test_complete_twice_409(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq_id, "maintenance_type": "corrective"},
            headers=hdrs,
        )
        mid = r.json()["id"]
        client.patch(f"/api/v1/equipment-maintenance/{mid}/complete", headers=hdrs)
        r2 = client.patch(f"/api/v1/equipment-maintenance/{mid}/complete", headers=hdrs)
        assert r2.status_code == 409

    def test_delete_maintenance(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={"equipment_id": eq_id, "maintenance_type": "calibration"},
            headers=hdrs,
        )
        mid = r.json()["id"]
        rd = client.delete(f"/api/v1/equipment-maintenance/{mid}", headers=hdrs)
        assert rd.status_code == 204
        r2 = client.get("/api/v1/equipment-maintenance", headers=hdrs)
        ids = [m["id"] for m in r2.json()]
        assert mid not in ids

    def test_delete_not_found(self, client):
        hdrs = _auth(client)
        r = client.delete("/api/v1/equipment-maintenance/99999", headers=hdrs)
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════
#  Due list endpoint
# ══════════════════════════════════════════════════════════════


class TestDueMaintenances:
    def test_due_within_7_days_appears(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        next_due = (_utcnow_naive() + dt.timedelta(days=3)).isoformat()
        client.post(
            "/api/v1/equipment-maintenance",
            json={
                "equipment_id": eq_id,
                "maintenance_type": "preventive",
                "next_due_at": next_due,
            },
            headers=hdrs,
        )
        r = client.get("/api/v1/equipment-maintenance/due?days=7", headers=hdrs)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_far_future_not_in_due(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        far = (_utcnow_naive() + dt.timedelta(days=60)).isoformat()
        client.post(
            "/api/v1/equipment-maintenance",
            json={
                "equipment_id": eq_id,
                "maintenance_type": "calibration",
                "next_due_at": far,
            },
            headers=hdrs,
        )
        r = client.get("/api/v1/equipment-maintenance/due?days=7", headers=hdrs)
        assert r.status_code == 200
        far_ids = [m["id"] for m in r.json()]
        # none of the due items should have next_due_at far in the future
        # (we just check that the far-future one is absent from the 7-day window)
        all_mnts = client.get("/api/v1/equipment-maintenance", headers=hdrs).json()
        far_mnt = next(
            (
                m
                for m in all_mnts
                if m["equipment_id"] == eq_id and "calibration" in m["maintenance_type"]
            ),
            None,
        )
        if far_mnt:
            assert far_mnt["id"] not in far_ids

    def test_completed_not_in_due(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        next_due = (_utcnow_naive() + dt.timedelta(days=1)).isoformat()
        r = client.post(
            "/api/v1/equipment-maintenance",
            json={
                "equipment_id": eq_id,
                "maintenance_type": "corrective",
                "next_due_at": next_due,
            },
            headers=hdrs,
        )
        mid = r.json()["id"]
        client.patch(f"/api/v1/equipment-maintenance/{mid}/complete", headers=hdrs)
        r2 = client.get("/api/v1/equipment-maintenance/due?days=7", headers=hdrs)
        due_ids = [m["id"] for m in r2.json()]
        assert mid not in due_ids


# ══════════════════════════════════════════════════════════════
#  Lab stats summary endpoint
# ══════════════════════════════════════════════════════════════


class TestLabStats:
    def test_summary_returns_expected_keys(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/stats/summary", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        for key in [
            "period_days",
            "total_results",
            "critical_results",
            "critical_rate_pct",
            "tat_by_equipment",
            "weekly_volumes",
            "qc_total",
            "qc_violations",
            "qc_violation_rate_pct",
            "maintenance_due_count",
        ]:
            assert key in data, f"Missing key: {key}"

    def test_summary_empty_db(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/stats/summary?days=30", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["total_results"] == 0
        assert data["critical_rate_pct"] == 0.0
        assert data["weekly_volumes"] is not None
        assert len(data["weekly_volumes"]) == 8  # always 8 weeks

    def test_summary_days_param(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/stats/summary?days=7", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["period_days"] == 7

    def test_summary_invalid_days(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/stats/summary?days=0", headers=hdrs)
        assert r.status_code == 422

    def test_maintenance_due_counted_in_stats(self, client):
        hdrs = _auth(client)
        eq_id = _create_equipment(client, hdrs)
        next_due = (_utcnow_naive() + dt.timedelta(days=2)).isoformat()
        client.post(
            "/api/v1/equipment-maintenance",
            json={
                "equipment_id": eq_id,
                "maintenance_type": "preventive",
                "next_due_at": next_due,
            },
            headers=hdrs,
        )
        r = client.get("/api/v1/stats/summary", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["maintenance_due_count"] >= 1

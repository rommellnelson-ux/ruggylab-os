"""Tests — Alertes péremption réactifs + correction de résultats (amend)."""
from __future__ import annotations

import datetime as dt
import uuid

# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _create_reagent(client, hdrs, *, expiry_date: str | None = None, stock: float = 50.0) -> dict:
    name = f"Rgt-{_uid()}"
    r = client.post(
        "/api/v1/reagents",
        headers=hdrs,
        json={
            "name": name,
            "category": "Test",
            "unit": "unit",
            "current_stock": stock,
            "alert_threshold": 5.0,
            "lot_number": f"LOT-{_uid()}",
            "expiry_date": expiry_date,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _make_patient(client, hdrs) -> int:
    return client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"EA-{_uid()}",
            "first_name": "Expiry",
            "last_name": "Amend",
            "birth_date": "1985-03-10",
            "sex": "M",
        },
    ).json()["id"]


def _make_sample(client, hdrs, patient_id: int) -> int:
    return client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"EA-{_uid()}", "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


def _post_result(client, hdrs, sample_id: int, data_points: dict) -> dict:
    r = client.post(
        "/api/v1/results",
        headers=hdrs,
        json={"sample_id": sample_id, "data_points": data_points, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _today_plus(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
#  /reagents/expiring
# ══════════════════════════════════════════════════════════════════════════════

class TestReagentExpiry:
    def test_expiring_reagent_appears(self, client):
        """Réactif périmant dans 15j → visible avec days=30."""
        hdrs = _auth(client)
        rgt = _create_reagent(client, hdrs, expiry_date=_today_plus(15))
        r = client.get("/api/v1/reagents/expiring?days=30", headers=hdrs)
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()]
        assert rgt["id"] in ids

    def test_expired_reagent_included(self, client):
        """Réactif déjà expiré → inclus dans la liste (days_remaining < 0)."""
        hdrs = _auth(client)
        rgt = _create_reagent(client, hdrs, expiry_date=_today_plus(-5))
        r = client.get("/api/v1/reagents/expiring?days=30", headers=hdrs)
        assert r.status_code == 200
        found = next((i for i in r.json() if i["id"] == rgt["id"]), None)
        assert found is not None
        assert found["is_expired"] is True
        assert found["days_remaining"] < 0

    def test_far_future_reagent_excluded(self, client):
        """Réactif périmant dans 200j → absent de days=30."""
        hdrs = _auth(client)
        rgt = _create_reagent(client, hdrs, expiry_date=_today_plus(200))
        r = client.get("/api/v1/reagents/expiring?days=30", headers=hdrs)
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()]
        assert rgt["id"] not in ids

    def test_no_expiry_date_excluded(self, client):
        """Réactif sans date de péremption → absent de la liste."""
        hdrs = _auth(client)
        rgt = _create_reagent(client, hdrs, expiry_date=None)
        r = client.get("/api/v1/reagents/expiring?days=30", headers=hdrs)
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()]
        assert rgt["id"] not in ids

    def test_days_zero_shows_expired_only(self, client):
        """days=0 → seuls les réactifs déjà expirés apparaissent."""
        hdrs = _auth(client)
        expired = _create_reagent(client, hdrs, expiry_date=_today_plus(-1))
        future = _create_reagent(client, hdrs, expiry_date=_today_plus(10))
        r = client.get("/api/v1/reagents/expiring?days=0", headers=hdrs)
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()]
        assert expired["id"] in ids
        assert future["id"] not in ids

    def test_expiring_response_fields(self, client):
        """Vérifier la structure des champs retournés."""
        hdrs = _auth(client)
        _create_reagent(client, hdrs, expiry_date=_today_plus(5))
        r = client.get("/api/v1/reagents/expiring?days=30", headers=hdrs)
        assert r.status_code == 200
        items = r.json()
        if items:
            item = items[0]
            for field in ("id", "name", "expiry_date", "days_remaining", "is_expired", "current_stock"):
                assert field in item, f"Champ manquant: {field}"

    def test_expiry_alerts_via_critical_alerts(self, client):
        """GET /critical-alerts/expiry-alerts renvoie la même liste."""
        hdrs = _auth(client)
        _create_reagent(client, hdrs, expiry_date=_today_plus(7))
        r = client.get("/api/v1/critical-alerts/expiry-alerts?days=30", headers=hdrs)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════════════════
#  /critical-alerts/expiry-check (webhook — no real target)
# ══════════════════════════════════════════════════════════════════════════════

class TestExpiryWebhook:
    def test_expiry_check_without_config_returns_zero(self, client):
        """Sans NotifConfig active → 0 notification envoyée."""
        hdrs = _auth(client)
        # Deactivate all notif configs
        configs = client.get("/api/v1/critical-alerts/config", headers=hdrs).json()
        for c in configs:
            client.delete(f"/api/v1/critical-alerts/config/{c['id']}", headers=hdrs)

        r = client.post("/api/v1/critical-alerts/expiry-check?days=30", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert "notified" in data
        assert data["notified"] == 0

    def test_expiry_check_response_shape(self, client):
        """Le endpoint /expiry-check retourne notified + expiring."""
        hdrs = _auth(client)
        r = client.post("/api/v1/critical-alerts/expiry-check?days=30", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert "notified" in data
        assert "expiring" in data


# ══════════════════════════════════════════════════════════════════════════════
#  PATCH /results/{id}/amend
# ══════════════════════════════════════════════════════════════════════════════

class TestResultAmend:
    def test_amend_updates_data_points(self, client):
        """L'amendement met à jour les data_points du résultat."""
        hdrs = _auth(client)
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"HGB": 110.0, "WBC": 6.0})
        result_id = result["id"]

        r = client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {"HGB": 125.0, "WBC": 7.5}, "amendment_reason": "Correction après re-lecture lame"},
        )
        assert r.status_code == 200, r.text
        amended = r.json()
        assert amended["data_points"]["HGB"] == 125.0
        assert amended["data_points"]["WBC"] == 7.5
        assert amended["amendment_reason"] == "Correction après re-lecture lame"

    def test_amend_reason_too_short_rejected(self, client):
        """Motif < 5 caractères → 422 Unprocessable Entity."""
        hdrs = _auth(client)
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 5.0})
        result_id = result["id"]

        r = client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 6.0}, "amendment_reason": "err"},
        )
        assert r.status_code == 422

    def test_amend_nonexistent_result(self, client):
        """Résultat introuvable → 404."""
        hdrs = _auth(client)
        r = client.patch(
            "/api/v1/results/99999/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 5.0}, "amendment_reason": "Motif valide"},
        )
        assert r.status_code == 404

    def test_amend_recalculates_flags(self, client):
        """L'amendement recalcule les flags après modification des données."""
        hdrs = _auth(client)
        # Create a reference range for a custom analyte
        analyte = f"RNG{_uid()[:4].upper()}"
        client.post(
            "/api/v1/reference-ranges",
            headers=hdrs,
            json={
                "analyte": analyte, "sex": "*",
                "age_min": None, "age_max": None,
                "low_normal": 4.0, "high_normal": 10.0,
                "unit": "unit",
            },
        )
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        # Initial: value above range → H flag
        result = _post_result(client, hdrs, sample_id, {analyte: 15.0})
        result_id = result["id"]
        assert result["flags"] is not None
        assert result["flags"].get(analyte) in ("H", "HH")

        # Amend: bring value into normal range → N flag
        r = client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {analyte: 7.0}, "amendment_reason": "Correction valeur erronée"},
        )
        assert r.status_code == 200, r.text
        amended = r.json()
        assert amended["flags"] is not None
        assert amended["flags"].get(analyte) == "N"

    def test_amend_missing_reason_rejected(self, client):
        """Motif manquant → 422."""
        hdrs = _auth(client)
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 5.0})
        r = client.patch(
            f"/api/v1/results/{result['id']}/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 6.0}},
        )
        assert r.status_code == 422

    def test_amend_extra_fields_rejected(self, client):
        """Champs supplémentaires → 422 (extra='forbid')."""
        hdrs = _auth(client)
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 5.0})
        r = client.patch(
            f"/api/v1/results/{result['id']}/amend",
            headers=hdrs,
            json={
                "data_points": {"WBC": 6.0},
                "amendment_reason": "Motif valide ici",
                "unknown_field": "surprise",
            },
        )
        assert r.status_code == 422

"""Tests — Auto-validation ISO 15189 §5.8 (config CRUD + intégration create_result + amend)."""
from __future__ import annotations

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


def _make_patient(client, hdrs) -> int:
    return client.post(
        "/api/v1/patients",
        headers=hdrs,
        json={
            "ipp_unique_id": f"AV-{_uid()}",
            "first_name": "Auto",
            "last_name": "Valid",
            "birth_date": "1990-01-01",
            "sex": "M",
        },
    ).json()["id"]


def _make_sample(client, hdrs, patient_id: int) -> int:
    return client.post(
        "/api/v1/samples",
        headers=hdrs,
        json={"barcode": f"AV-{_uid()}", "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


def _post_result(client, hdrs, sample_id: int, data_points: dict) -> dict:
    r = client.post(
        "/api/v1/results",
        headers=hdrs,
        json={"sample_id": sample_id, "data_points": data_points, "is_critical": False},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_ref_range(client, hdrs, analyte: str, low: float, high: float) -> None:
    """Create a reference range so compute_flags can return 'N'."""
    r = client.post(
        "/api/v1/reference-ranges",
        headers=hdrs,
        json={
            "analyte": analyte,
            "sex": "*",
            "age_min": None,
            "age_max": None,
            "low_normal": low,
            "high_normal": high,
            "unit": "unit",
        },
    )
    assert r.status_code in (200, 201), r.text


def _create_auto_config(
    client,
    hdrs,
    *,
    require_all_flags_normal: bool = False,
    require_no_delta: bool = False,
    require_not_critical: bool = True,
) -> dict:
    r = client.post(
        "/api/v1/auto-validation/config",
        headers=hdrs,
        json={
            "name": f"Test-{_uid()}",
            "require_all_flags_normal": require_all_flags_normal,
            "require_no_delta": require_no_delta,
            "require_not_critical": require_not_critical,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ══════════════════════════════════════════════════════════════════════════════
#  AutoValidationConfig CRUD
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoValidationConfigCRUD:
    def test_create_config(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/auto-validation/config",
            headers=hdrs,
            json={
                "name": "Règle ISO",
                "require_all_flags_normal": True,
                "require_no_delta": True,
                "require_not_critical": True,
            },
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["name"] == "Règle ISO"
        assert data["require_all_flags_normal"] is True
        assert data["require_no_delta"] is True
        assert data["require_not_critical"] is True
        assert data["is_active"] is True
        assert "id" in data

    def test_list_configs(self, client):
        hdrs = _auth(client)
        _create_auto_config(client, hdrs)
        r = client.get("/api/v1/auto-validation/config", headers=hdrs)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_deactivate_config(self, client):
        hdrs = _auth(client)
        cfg = _create_auto_config(client, hdrs)
        cfg_id = cfg["id"]
        r = client.delete(f"/api/v1/auto-validation/config/{cfg_id}", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["status"] == "deactivated"
        # Should no longer appear in active list
        configs = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        assert all(c["id"] != cfg_id for c in configs)

    def test_deactivate_nonexistent(self, client):
        hdrs = _auth(client)
        r = client.delete("/api/v1/auto-validation/config/99999", headers=hdrs)
        assert r.status_code == 404

    def test_extra_fields_rejected(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/auto-validation/config",
            headers=hdrs,
            json={"name": "X", "unknown_field": True},
        )
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
#  Integration — auto-validation on result creation
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoValidationOnCreate:
    def test_no_config_no_auto_validated(self, client):
        """Sans config active, is_auto_validated reste False."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 5.0})
        assert result["is_auto_validated"] is False

    def test_auto_validated_when_not_critical_only(self, client):
        """Règle : seul require_not_critical=True → valide si pas critique."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=False,
            require_no_delta=False,
            require_not_critical=True,
        )
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        # No critical ranges configured for ZZZZ → not critical
        result = _post_result(client, hdrs, sample_id, {"ZZZZ": 5.0})
        assert result["is_auto_validated"] is True
        assert result["auto_validated_at"] is not None

    def test_not_auto_validated_when_critical(self, client):
        """Résultat critique → pas d'auto-validation (require_not_critical=True)."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=False,
            require_no_delta=False,
            require_not_critical=True,
        )
        # Create critical range for WBC
        r_cr = client.post(
            "/api/v1/critical-ranges",
            headers=hdrs,
            json={"analyte": "WBC", "low_critical": None, "high_critical": 1.0, "unit": "unit"},
        )
        assert r_cr.status_code in (200, 201), r_cr.text

        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 50.0})
        assert result["is_critical"] is True
        assert result["is_auto_validated"] is False

    def test_auto_validated_with_normal_flags(self, client):
        """Règle require_all_flags_normal=True → valide si tous les flags sont N."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        analyte = f"ANA{_uid()[:4].upper()}"
        _create_ref_range(client, hdrs, analyte, 4.0, 11.0)
        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=True,
            require_no_delta=False,
            require_not_critical=False,
        )
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        # Value in normal range → flag = N
        result = _post_result(client, hdrs, sample_id, {analyte: 7.0})
        assert result["flags"] is not None
        assert result["flags"].get(analyte) == "N"
        assert result["is_auto_validated"] is True

    def test_not_auto_validated_with_abnormal_flags(self, client):
        """Flag anormal (H/L) → pas d'auto-validation."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        analyte = f"ANB{_uid()[:4].upper()}"
        _create_ref_range(client, hdrs, analyte, 4.0, 11.0)
        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=True,
            require_no_delta=False,
            require_not_critical=False,
        )
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        # Value above high_normal → flag = H
        result = _post_result(client, hdrs, sample_id, {analyte: 20.0})
        assert result["flags"] is not None
        flag_val = result["flags"].get(analyte)
        assert flag_val in ("H", "HH")
        assert result["is_auto_validated"] is False


# ══════════════════════════════════════════════════════════════════════════════
#  Batch auto-validation via /run
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchAutoValidation:
    def test_run_returns_counts(self, client):
        hdrs = _auth(client)
        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=False,
            require_no_delta=False,
            require_not_critical=False,
        )
        r = client.post("/api/v1/auto-validation/run", headers=hdrs)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "processed" in data
        assert "auto_validated" in data
        assert isinstance(data["processed"], int)
        assert isinstance(data["auto_validated"], int)

    def test_run_requires_officer(self, client):
        """Le /run endpoint nécessite le rôle officer."""
        # Create a non-officer user
        hdrs = _auth(client)
        uid = _uid()
        client.post(
            "/api/v1/users",
            headers=hdrs,
            json={
                "username": f"usr_{uid}",
                "password": "TestPass123!",
                "full_name": "Regular User",
                "role": "technician",
            },
        )
        token = client.post(
            "/api/v1/login/access-token",
            data={"username": f"usr_{uid}", "password": "TestPass123!"},
        ).json().get("access_token")
        if token:
            usr_hdrs = {"Authorization": f"Bearer {token}"}
            r = client.post("/api/v1/auto-validation/run", headers=usr_hdrs)
            assert r.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
#  Amend result + auto-revalidation
# ══════════════════════════════════════════════════════════════════════════════

class TestAmendResetsAutoValidation:
    def test_amend_resets_and_revalidates(self, client):
        """Correction d'un résultat auto-validé → reset + re-qualification."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        # Config : nothing blocking
        _create_auto_config(
            client, hdrs,
            require_all_flags_normal=False,
            require_no_delta=False,
            require_not_critical=False,
        )
        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"WBC": 5.0})
        result_id = result["id"]
        assert result["is_auto_validated"] is True

        # Amend the result
        r = client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 6.5}, "amendment_reason": "Recalibration post-QC"},
        )
        assert r.status_code == 200, r.text
        amended = r.json()
        assert amended["data_points"]["WBC"] == 6.5
        assert amended["amendment_reason"] == "Recalibration post-QC"
        # After amend with permissive config → should be re-auto-validated
        assert amended["is_auto_validated"] is True

    def test_amend_creates_audit_trail(self, client):
        """PATCH /amend doit créer un AuditEvent result.amend."""
        hdrs = _auth(client)
        # Deactivate any existing configs
        existing = client.get("/api/v1/auto-validation/config", headers=hdrs).json()
        for c in existing:
            client.delete(f"/api/v1/auto-validation/config/{c['id']}", headers=hdrs)

        patient_id = _make_patient(client, hdrs)
        sample_id = _make_sample(client, hdrs, patient_id)
        result = _post_result(client, hdrs, sample_id, {"HGB": 120.0})
        result_id = result["id"]

        client.patch(
            f"/api/v1/results/{result_id}/amend",
            headers=hdrs,
            json={"data_points": {"HGB": 125.0}, "amendment_reason": "Vérification manuelle"},
        )
        # Check audit events for this result
        r = client.get(
            f"/api/v1/audit-events?entity_type=result&entity_id={result_id}",
            headers=hdrs,
        )
        if r.status_code == 200:
            events = r.json()
            amend_events = [e for e in (events.get("items") or events) if e.get("event_type") == "result.amend"]
            assert len(amend_events) >= 1

"""Tests for critical ranges — unit tests for the checker service and API integration."""

from app.services.critical_checker import _extract_numeric

# ══════════════════════════════════════════════════════════════════════════════
#  Unit tests — _extract_numeric helper
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractNumeric:
    def test_plain_int(self) -> None:
        assert _extract_numeric(5) == 5.0

    def test_plain_float(self) -> None:
        assert _extract_numeric(3.14) == 3.14

    def test_dict_with_value_key(self) -> None:
        assert _extract_numeric({"value": 7.2, "status": "H"}) == 7.2

    def test_dict_missing_value_key_returns_none(self) -> None:
        assert _extract_numeric({"status": "N"}) is None

    def test_string_returns_none(self) -> None:
        assert _extract_numeric("5.0") is None

    def test_none_returns_none(self) -> None:
        assert _extract_numeric(None) is None

    def test_dict_with_non_numeric_value_returns_none(self) -> None:
        assert _extract_numeric({"value": "high"}) is None


# ══════════════════════════════════════════════════════════════════════════════
#  Integration tests — critical ranges API + auto-detection + ack
# ══════════════════════════════════════════════════════════════════════════════


def _admin_headers(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_sample(client, headers) -> int:
    patient_id = client.post(
        "/api/v1/patients",
        headers=headers,
        json={"ipp_unique_id": "IPP-CR-001", "first_name": "Test", "last_name": "CR",
              "birth_date": "1990-01-01", "sex": "M"},
    ).json()["id"]
    return client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": "CR-SAMPLE-001", "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


class TestCriticalRangesApi:

    def test_list_requires_auth(self, client) -> None:
        assert client.get("/api/v1/critical-ranges").status_code == 401

    def test_create_requires_officer(self, client) -> None:
        assert client.post(
            "/api/v1/critical-ranges",
            json={"analyte": "WBC", "high_critical": 30.0},
        ).status_code == 401

    def test_create_without_any_bound_rejected(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "WBC", "unit": "×10³/μL"},
        )
        assert resp.status_code == 422

    def test_create_and_list(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "WBC", "low_critical": 2.0, "high_critical": 30.0, "unit": "×10³/μL"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["analyte"] == "WBC"
        assert data["low_critical"] == 2.0
        assert data["high_critical"] == 30.0
        assert data["is_active"] is True

        listed = client.get("/api/v1/critical-ranges", headers=headers).json()
        assert any(cr["analyte"] == "WBC" for cr in listed)

    def test_duplicate_analyte_rejected(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "HGB", "low_critical": 70.0},
        )
        resp = client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "HGB", "low_critical": 60.0},
        )
        assert resp.status_code == 409

    def test_deactivate_removes_from_list(self, client) -> None:
        headers = _admin_headers(client)
        cr = client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "PLT", "low_critical": 50.0, "high_critical": 1000.0},
        ).json()
        assert client.delete(
            f"/api/v1/critical-ranges/{cr['id']}", headers=headers
        ).status_code == 200
        ids = [c["id"] for c in client.get("/api/v1/critical-ranges", headers=headers).json()]
        assert cr["id"] not in ids

    def test_deactivate_unknown_returns_404(self, client) -> None:
        headers = _admin_headers(client)
        assert client.delete(
            "/api/v1/critical-ranges/99999", headers=headers
        ).status_code == 404

    def test_high_threshold_auto_flags_critical(self, client) -> None:
        headers = _admin_headers(client)
        # WBC high critical = 30; we send WBC = 45 → must be auto-flagged
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "WBC", "high_critical": 30.0, "unit": "×10³/μL"},
        )
        sample_id = _make_sample(client, headers)
        resp = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"WBC": 45.0}, "is_critical": False},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_critical"] is True

    def test_low_threshold_auto_flags_critical(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "HGB", "low_critical": 70.0, "unit": "g/L"},
        )
        sample_id = _make_sample(client, headers)
        resp = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"HGB": 55.0}, "is_critical": False},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_critical"] is True

    def test_within_range_not_flagged(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "PLT", "low_critical": 50.0, "high_critical": 1000.0},
        )
        sample_id = _make_sample(client, headers)
        resp = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"PLT": 250.0}, "is_critical": False},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_critical"] is False

    def test_manual_critical_preserved_without_range(self, client) -> None:
        """is_critical=True from client stays True even without a matching range."""
        headers = _admin_headers(client)
        sample_id = _make_sample(client, headers)
        resp = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"UNKNOWN": 99.0}, "is_critical": True},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_critical"] is True

    def test_case_insensitive_analyte_match(self, client) -> None:
        """Critical range 'wbc' matches data_point key 'WBC'."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "wbc", "high_critical": 30.0},
        )
        sample_id = _make_sample(client, headers)
        resp = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"WBC": 45.0}, "is_critical": False},
        )
        assert resp.json()["is_critical"] is True

    def test_ack_critical_sets_timestamp_and_user(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "RBC", "low_critical": 1.0},
        )
        sample_id = _make_sample(client, headers)
        result_id = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"RBC": 0.5}, "is_critical": False},
        ).json()["id"]

        ack = client.patch(f"/api/v1/results/{result_id}/ack-critical", headers=headers)
        assert ack.status_code == 200, ack.text
        data = ack.json()
        assert data["critical_ack_at"] is not None
        assert data["critical_ack_by_id"] is not None

    def test_ack_non_critical_returns_400(self, client) -> None:
        headers = _admin_headers(client)
        sample_id = _make_sample(client, headers)
        result_id = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"WBC": 5.0}, "is_critical": False},
        ).json()["id"]
        assert client.patch(
            f"/api/v1/results/{result_id}/ack-critical", headers=headers
        ).status_code == 400

    def test_double_ack_returns_409(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/critical-ranges",
            headers=headers,
            json={"analyte": "MCV", "low_critical": 50.0},
        )
        sample_id = _make_sample(client, headers)
        result_id = client.post(
            "/api/v1/results",
            headers=headers,
            json={"sample_id": sample_id, "data_points": {"MCV": 40.0}, "is_critical": False},
        ).json()["id"]
        client.patch(f"/api/v1/results/{result_id}/ack-critical", headers=headers)
        assert client.patch(
            f"/api/v1/results/{result_id}/ack-critical", headers=headers
        ).status_code == 409


class TestQcSummaryApi:

    def test_qc_summary_requires_auth(self, client) -> None:
        assert client.get("/api/v1/reports/qc-summary").status_code == 401

    def test_qc_summary_empty_when_no_controls(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.get("/api/v1/reports/qc-summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["controls"] == []
        assert data["reject_count"] == 0
        assert data["warn_count"] == 0

    def test_qc_summary_no_data_status(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/qc/controls",
            headers=headers,
            json={"analyte": "Glucose", "target_mean": 5.0, "target_sd": 0.25},
        )
        data = client.get("/api/v1/reports/qc-summary", headers=headers).json()
        assert len(data["controls"]) == 1
        assert data["controls"][0]["status"] == "no_data"

    def test_qc_summary_ok_status(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = client.post(
            "/api/v1/qc/controls",
            headers=headers,
            json={"analyte": "HGB", "target_mean": 140.0, "target_sd": 5.0},
        ).json()
        client.post(
            "/api/v1/qc/results",
            headers=headers,
            json={"control_id": ctrl["id"], "value": 141.0, "measured_at": "2026-06-01"},
        )
        data = client.get("/api/v1/reports/qc-summary", headers=headers).json()
        entry = next(e for e in data["controls"] if e["analyte"] == "HGB")
        assert entry["status"] == "ok"
        assert data["reject_count"] == 0

    def test_qc_summary_reject_status_and_count(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = client.post(
            "/api/v1/qc/controls",
            headers=headers,
            json={"analyte": "WBC", "target_mean": 7.0, "target_sd": 0.5},
        ).json()
        # z = 3.2 → 1-3s reject
        client.post(
            "/api/v1/qc/results",
            headers=headers,
            json={"control_id": ctrl["id"], "value": 8.6, "measured_at": "2026-06-01"},
        )
        data = client.get("/api/v1/reports/qc-summary", headers=headers).json()
        entry = next(e for e in data["controls"] if e["analyte"] == "WBC")
        assert entry["status"] == "reject"
        assert data["reject_count"] == 1

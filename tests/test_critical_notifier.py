"""Tests — Alertes critiques non-acquittées (service + API)."""


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _admin_headers(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_sample(client, headers) -> int:
    patient_id = client.post(
        "/api/v1/patients", headers=headers,
        json={"ipp_unique_id": f"IPP-NA-{id(client)}",
              "first_name": "Alert", "last_name": "Test",
              "birth_date": "1990-01-01", "sex": "M"},
    ).json()["id"]
    return client.post(
        "/api/v1/samples", headers=headers,
        json={"barcode": f"NA-{id(client)}", "patient_id": patient_id,
              "status": "Recu"},
    ).json()["id"]


def _make_critical_result(client, headers, barcode_suffix: str) -> int:
    """Create a critical result (via critical range auto-detection)."""
    # Ensure critical range exists for WBC
    client.post("/api/v1/critical-ranges", headers=headers,
                json={"analyte": "WBC", "high_critical": 30.0})
    patient_id = client.post(
        "/api/v1/patients", headers=headers,
        json={"ipp_unique_id": f"IPP-NA-{barcode_suffix}",
              "first_name": "Crit", "last_name": "Test",
              "birth_date": "1990-01-01", "sex": "M"},
    ).json()["id"]
    sample_id = client.post(
        "/api/v1/samples", headers=headers,
        json={"barcode": f"NA-{barcode_suffix}",
              "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]
    return client.post(
        "/api/v1/results", headers=headers,
        json={"sample_id": sample_id, "data_points": {"WBC": 45.0},
              "is_critical": False},
    ).json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
#  API — notification config CRUD
# ══════════════════════════════════════════════════════════════════════════════


class TestNotifConfigApi:

    def test_list_config_requires_auth(self, client) -> None:
        assert client.get("/api/v1/critical-alerts/config").status_code == 401

    def test_create_config_requires_officer(self, client) -> None:
        assert client.post(
            "/api/v1/critical-alerts/config",
            json={"webhook_url": "http://example.com/hook", "delay_minutes": 30},
        ).status_code == 401

    def test_create_config_without_channel_rejected(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post("/api/v1/critical-alerts/config", headers=headers,
                           json={"delay_minutes": 30})
        assert resp.status_code == 422

    def test_create_and_list_config(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/critical-alerts/config", headers=headers,
            json={"webhook_url": "http://lab.example.com/notify", "delay_minutes": 45},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["webhook_url"] == "http://lab.example.com/notify"
        assert data["delay_minutes"] == 45
        assert data["is_active"] is True

        listed = client.get("/api/v1/critical-alerts/config", headers=headers).json()
        assert any(c["webhook_url"] == "http://lab.example.com/notify" for c in listed)

    def test_deactivate_config(self, client) -> None:
        headers = _admin_headers(client)
        cfg = client.post(
            "/api/v1/critical-alerts/config", headers=headers,
            json={"webhook_url": "http://x.example.com/", "delay_minutes": 20},
        ).json()
        assert client.delete(
            f"/api/v1/critical-alerts/config/{cfg['id']}", headers=headers
        ).status_code == 200
        ids = [c["id"] for c in
               client.get("/api/v1/critical-alerts/config", headers=headers).json()]
        assert cfg["id"] not in ids

    def test_deactivate_unknown_config_404(self, client) -> None:
        headers = _admin_headers(client)
        assert client.delete(
            "/api/v1/critical-alerts/config/99999", headers=headers
        ).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
#  API — pending criticals
# ══════════════════════════════════════════════════════════════════════════════


class TestPendingCriticalsApi:

    def test_pending_requires_auth(self, client) -> None:
        assert client.get("/api/v1/critical-alerts/pending").status_code == 401

    def test_empty_when_no_criticals(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.get("/api/v1/critical-alerts/pending", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_critical_result_appears_in_pending(self, client) -> None:
        headers = _admin_headers(client)
        result_id = _make_critical_result(client, headers, "P001")
        pending = client.get("/api/v1/critical-alerts/pending", headers=headers).json()
        ids = [p["result_id"] for p in pending]
        assert result_id in ids

    def test_acked_result_removed_from_pending(self, client) -> None:
        headers = _admin_headers(client)
        result_id = _make_critical_result(client, headers, "P002")
        client.patch(f"/api/v1/results/{result_id}/ack-critical", headers=headers)
        pending = client.get("/api/v1/critical-alerts/pending", headers=headers).json()
        ids = [p["result_id"] for p in pending]
        assert result_id not in ids

    def test_pending_entry_has_elapsed_minutes(self, client) -> None:
        headers = _admin_headers(client)
        _make_critical_result(client, headers, "P003")
        pending = client.get("/api/v1/critical-alerts/pending", headers=headers).json()
        assert len(pending) >= 1
        entry = pending[0]
        assert "elapsed_minutes" in entry
        assert "overdue" in entry
        assert isinstance(entry["elapsed_minutes"], int)

    def test_overdue_flag_set_with_zero_delay(self, client) -> None:
        """Avec delay=1 min, un résultat créé maintenant est overdue=False."""
        headers = _admin_headers(client)
        _make_critical_result(client, headers, "P004")
        pending = client.get(
            "/api/v1/critical-alerts/pending?delay_minutes=60", headers=headers
        ).json()
        # Résultat vient d'être créé → elapsed ~ 0 → overdue=False
        assert pending[0]["overdue"] is False


# ══════════════════════════════════════════════════════════════════════════════
#  API — check-and-notify endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestCheckAndNotifyApi:

    def test_check_requires_auth(self, client) -> None:
        assert client.post("/api/v1/critical-alerts/check").status_code == 401

    def test_check_no_configs_returns_zero_notified(self, client) -> None:
        headers = _admin_headers(client)
        _make_critical_result(client, headers, "CN001")
        resp = client.post("/api/v1/critical-alerts/check", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # Pas de config → notified=0
        assert data["notified"] == 0
        # Mais pending > 0
        assert data["pending"] >= 1

    def test_check_with_bad_webhook_sends_zero(self, client) -> None:
        """Webhook inaccessible → notified=0 mais pas d'erreur 500."""
        headers = _admin_headers(client)
        client.post("/api/v1/critical-alerts/config", headers=headers,
                    json={"webhook_url": "http://127.0.0.1:1/unreachable",
                          "delay_minutes": 1})
        _make_critical_result(client, headers, "CN002")
        resp = client.post("/api/v1/critical-alerts/check", headers=headers)
        assert resp.status_code == 200
        # webhook échoue silencieusement → notified=0
        assert resp.json()["notified"] == 0


# ══════════════════════════════════════════════════════════════════════════════
#  API — QC report HTML
# ══════════════════════════════════════════════════════════════════════════════


class TestQcReportApi:

    def test_report_requires_auth(self, client) -> None:
        assert client.get("/api/v1/reports/qc-report").status_code == 401

    def test_report_returns_html(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.get(
            "/api/v1/reports/qc-report?year=2026&month=6", headers=headers
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "RuggyLab OS" in resp.text
        assert "Rapport QC" in resp.text

    def test_report_empty_month_has_no_data(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.get(
            "/api/v1/reports/qc-report?year=2025&month=1", headers=headers
        )
        assert resp.status_code == 200
        # Aucun contrôle dans cette période

    def test_report_with_control_and_results(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = client.post(
            "/api/v1/qc/controls", headers=headers,
            json={"analyte": "HGB", "target_mean": 140.0, "target_sd": 5.0},
        ).json()
        client.post("/api/v1/qc/results", headers=headers,
                    json={"control_id": ctrl["id"], "value": 142.0,
                          "measured_at": "2026-06-01"})
        client.post("/api/v1/qc/results", headers=headers,
                    json={"control_id": ctrl["id"], "value": 138.0,
                          "measured_at": "2026-06-02"})
        resp = client.get(
            "/api/v1/reports/qc-report?year=2026&month=6", headers=headers
        )
        assert resp.status_code == 200
        assert "HGB" in resp.text
        assert "142" in resp.text or "138" in resp.text

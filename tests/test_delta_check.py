"""Tests — Delta-check patient (service + API + intégration create_result)."""


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _admin_headers(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_patient(client, headers, ipp: str = "IPP-DC-001") -> int:
    return client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": ipp,
            "first_name": "Delta",
            "last_name": "Test",
            "birth_date": "1985-06-15",
            "sex": "M",
        },
    ).json()["id"]


def _make_sample(client, headers, patient_id: int, barcode: str) -> int:
    return client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


def _post_result(client, headers, sample_id: int, data_points: dict) -> dict:
    return client.post(
        "/api/v1/results",
        headers=headers,
        json={"sample_id": sample_id, "data_points": data_points, "is_critical": False},
    ).json()


# ══════════════════════════════════════════════════════════════════════════════
#  API — delta-check rules CRUD
# ══════════════════════════════════════════════════════════════════════════════


class TestDeltaCheckRuleApi:
    def test_list_requires_auth(self, client) -> None:
        assert client.get("/api/v1/delta-check-rules").status_code == 401

    def test_create_requires_officer(self, client) -> None:
        assert (
            client.post(
                "/api/v1/delta-check-rules",
                json={"analyte": "HGB", "delta_pct": 20.0},
            ).status_code
            == 401
        )

    def test_create_without_threshold_rejected(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/delta-check-rules",
            headers=headers,
            json={"analyte": "HGB"},
        )
        assert resp.status_code == 422

    def test_create_and_list(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/delta-check-rules",
            headers=headers,
            json={"analyte": "HGB", "delta_pct": 20.0, "delta_abs": 30.0, "unit": "g/L"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["analyte"] == "HGB"
        assert data["delta_pct"] == 20.0
        assert data["is_active"] is True

        listed = client.get("/api/v1/delta-check-rules", headers=headers).json()
        assert any(r["analyte"] == "HGB" for r in listed)

    def test_duplicate_analyte_rejected(self, client) -> None:
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "WBC", "delta_pct": 30.0}
        )
        resp = client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "WBC", "delta_abs": 5.0}
        )
        assert resp.status_code == 409

    def test_deactivate_removes_from_list(self, client) -> None:
        headers = _admin_headers(client)
        rule = client.post(
            "/api/v1/delta-check-rules",
            headers=headers,
            json={"analyte": "PLT", "delta_abs": 100.0},
        ).json()
        assert (
            client.delete(f"/api/v1/delta-check-rules/{rule['id']}", headers=headers).status_code
            == 200
        )
        ids = [r["id"] for r in client.get("/api/v1/delta-check-rules", headers=headers).json()]
        assert rule["id"] not in ids

    def test_deactivate_unknown_returns_404(self, client) -> None:
        headers = _admin_headers(client)
        assert client.delete("/api/v1/delta-check-rules/99999", headers=headers).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
#  Integration — delta auto-detection on result creation
# ══════════════════════════════════════════════════════════════════════════════


class TestDeltaCheckIntegration:
    def test_first_result_no_delta(self, client) -> None:
        """Premier résultat pour un patient → pas de delta (pas de précédent)."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "HGB", "delta_abs": 20.0}
        )
        patient_id = _make_patient(client, headers, "IPP-DC-101")
        sample_id = _make_sample(client, headers, patient_id, "DC-S001")
        result = _post_result(client, headers, sample_id, {"HGB": 130.0})
        assert result["delta_exceeded"] is False
        assert not result.get("delta_analytes")

    def test_delta_abs_flagged(self, client) -> None:
        """Variation absolue > seuil → delta_exceeded=True."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "HGB", "delta_abs": 20.0}
        )
        patient_id = _make_patient(client, headers, "IPP-DC-102")
        # Résultat 1
        s1 = _make_sample(client, headers, patient_id, "DC-S101")
        _post_result(client, headers, s1, {"HGB": 130.0})
        # Résultat 2 : variation 40 g/L > seuil 20
        s2 = _make_sample(client, headers, patient_id, "DC-S102")
        result = _post_result(client, headers, s2, {"HGB": 90.0})
        assert result["delta_exceeded"] is True
        assert "HGB" in result["delta_analytes"]

    def test_delta_pct_flagged(self, client) -> None:
        """Variation en % > seuil → delta_exceeded=True."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "WBC", "delta_pct": 25.0}
        )
        patient_id = _make_patient(client, headers, "IPP-DC-103")
        s1 = _make_sample(client, headers, patient_id, "DC-S201")
        _post_result(client, headers, s1, {"WBC": 8.0})
        # Variation = -50% > seuil 25%
        s2 = _make_sample(client, headers, patient_id, "DC-S202")
        result = _post_result(client, headers, s2, {"WBC": 4.0})
        assert result["delta_exceeded"] is True

    def test_within_threshold_not_flagged(self, client) -> None:
        """Petite variation → pas de flag."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules",
            headers=headers,
            json={"analyte": "PLT", "delta_abs": 100.0},
        )
        patient_id = _make_patient(client, headers, "IPP-DC-104")
        s1 = _make_sample(client, headers, patient_id, "DC-S301")
        _post_result(client, headers, s1, {"PLT": 250.0})
        s2 = _make_sample(client, headers, patient_id, "DC-S302")
        result = _post_result(client, headers, s2, {"PLT": 270.0})
        assert result["delta_exceeded"] is False

    def test_no_patient_no_delta(self, client) -> None:
        """Échantillon sans patient → pas de delta-check possible."""
        headers = _admin_headers(client)
        client.post(
            "/api/v1/delta-check-rules", headers=headers, json={"analyte": "HGB", "delta_abs": 20.0}
        )
        sample_id = client.post(
            "/api/v1/samples",
            headers=headers,
            json={"barcode": "DC-NOPATIENT", "status": "Recu"},
        ).json()["id"]
        result = _post_result(client, headers, sample_id, {"HGB": 90.0})
        assert result["delta_exceeded"] is False

    def test_no_rule_no_delta(self, client) -> None:
        """Aucune règle → delta_exceeded=False."""
        headers = _admin_headers(client)
        patient_id = _make_patient(client, headers, "IPP-DC-105")
        s1 = _make_sample(client, headers, patient_id, "DC-S401")
        _post_result(client, headers, s1, {"HGB": 130.0})
        s2 = _make_sample(client, headers, patient_id, "DC-S402")
        result = _post_result(client, headers, s2, {"HGB": 50.0})
        # Pas de règle → pas de flag
        assert result["delta_exceeded"] is False

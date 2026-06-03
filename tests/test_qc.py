"""Tests for the Westgard multi-rule engine and QC API endpoints."""

from app.services.westgard import check_westgard

# ══════════════════════════════════════════════════════════════════════════════
#  Unit tests — Westgard rule engine
# ══════════════════════════════════════════════════════════════════════════════


class TestWestgardRules:
    """Each Westgard rule is tested individually and in combination."""

    # ── Guard cases ──────────────────────────────────────────────────────────

    def test_empty_values_returns_empty(self) -> None:
        assert check_westgard([], 100.0, 5.0) == []

    def test_zero_sd_returns_empty(self) -> None:
        """Division by zero must be handled gracefully."""
        assert check_westgard([100.0, 110.0], 100.0, 0.0) == []

    def test_in_control_no_violations(self) -> None:
        """Values scattered within ±1.5 SD → no rule violated."""
        values = [101.0, 99.5, 100.2, 98.8, 101.5]
        assert check_westgard(values, 100.0, 5.0) == []

    # ── 1-2s (warning) ───────────────────────────────────────────────────────

    def test_1_2s_positive_side(self) -> None:
        """z = +2.1 → 1-2s warning, not 1-3s."""
        violations = check_westgard([110.5], 100.0, 5.0)
        assert "1-2s" in violations
        assert "1-3s" not in violations

    def test_1_2s_negative_side(self) -> None:
        """z = -2.1 → 1-2s warning."""
        assert "1-2s" in check_westgard([89.5], 100.0, 5.0)

    # ── 1-3s (reject) ────────────────────────────────────────────────────────

    def test_1_3s_reject_positive(self) -> None:
        """z = +3.2 → 1-3s reject; 1-2s must NOT appear (elif branch)."""
        violations = check_westgard([116.0], 100.0, 5.0)
        assert "1-3s" in violations
        assert "1-2s" not in violations

    def test_1_3s_reject_negative(self) -> None:
        """z = -3.2 → 1-3s reject."""
        assert "1-3s" in check_westgard([84.0], 100.0, 5.0)

    # ── 2-2s (reject) ────────────────────────────────────────────────────────

    def test_2_2s_same_side_positive(self) -> None:
        """Two consecutive points both > +2 SD → 2-2s."""
        violations = check_westgard([100.0, 111.0, 112.0], 100.0, 5.0)
        assert "2-2s" in violations

    def test_2_2s_same_side_negative(self) -> None:
        """Two consecutive points both < -2 SD → 2-2s."""
        violations = check_westgard([100.0, 89.0, 88.0], 100.0, 5.0)
        assert "2-2s" in violations

    def test_2_2s_opposite_sides_not_triggered(self) -> None:
        """One above +2 SD, next below -2 SD (opposite sides) → no 2-2s."""
        violations = check_westgard([111.0, 89.0], 100.0, 5.0)
        assert "2-2s" not in violations

    # ── R-4s (reject) ────────────────────────────────────────────────────────

    def test_R4s_range_exceeds_4sd(self) -> None:
        """z1 = +2.5, z2 = -2.5 → range = 5 SD > 4 → R-4s."""
        violations = check_westgard([112.5, 87.5], 100.0, 5.0)
        assert "R-4s" in violations

    def test_R4s_exact_4sd_not_triggered(self) -> None:
        """Range exactly 4 SD (not strictly > 4) → no R-4s."""
        violations = check_westgard([110.0, 90.0], 100.0, 5.0)
        assert "R-4s" not in violations

    def test_R4s_single_value_not_evaluated(self) -> None:
        """Only one value → R-4s cannot be evaluated."""
        assert "R-4s" not in check_westgard([120.0], 100.0, 5.0)

    # ── 4-1s (reject) ────────────────────────────────────────────────────────

    def test_4_1s_positive_trend(self) -> None:
        """Four consecutive points all above +1 SD → 4-1s."""
        values = [106.0, 107.0, 108.0, 106.5]  # z ≈ 1.2, 1.4, 1.6, 1.3
        assert "4-1s" in check_westgard(values, 100.0, 5.0)

    def test_4_1s_negative_trend(self) -> None:
        """Four consecutive points all below -1 SD → 4-1s."""
        values = [94.0, 93.0, 92.0, 93.5]  # z ≈ -1.2, -1.4, -1.6, -1.3
        assert "4-1s" in check_westgard(values, 100.0, 5.0)

    def test_4_1s_three_not_enough(self) -> None:
        """Only 3 consecutive values beyond ±1 SD → no 4-1s."""
        values = [106.0, 107.0, 106.5]
        assert "4-1s" not in check_westgard(values, 100.0, 5.0)

    def test_4_1s_streak_broken(self) -> None:
        """Streak interrupted by an in-control value → no 4-1s."""
        values = [106.0, 99.0, 106.0, 107.0]
        assert "4-1s" not in check_westgard(values, 100.0, 5.0)

    # ── 10x (reject) ─────────────────────────────────────────────────────────

    def test_10x_ten_consecutive_positive(self) -> None:
        """Ten consecutive positive z-scores → 10x."""
        assert "10x" in check_westgard([101.0] * 10, 100.0, 5.0)

    def test_10x_ten_consecutive_negative(self) -> None:
        """Ten consecutive negative z-scores → 10x."""
        assert "10x" in check_westgard([99.0] * 10, 100.0, 5.0)

    def test_10x_nine_not_enough(self) -> None:
        """Only 9 consecutive same-side values → no 10x."""
        assert "10x" not in check_westgard([101.0] * 9, 100.0, 5.0)

    def test_10x_broken_streak(self) -> None:
        """Streak of 9 broken by one opposite-side value → no 10x."""
        values = [99.0] * 5 + [101.0] + [99.0] * 4
        assert "10x" not in check_westgard(values, 100.0, 5.0)

    # ── Multi-rule ────────────────────────────────────────────────────────────

    def test_multiple_violations_simultaneously(self) -> None:
        """9 positives + a 1-3s value → both 10x and 1-3s triggered."""
        values = [101.0] * 9 + [116.0]  # z of last = +3.2
        violations = check_westgard(values, 100.0, 5.0)
        assert "1-3s" in violations
        assert "10x" in violations


# ══════════════════════════════════════════════════════════════════════════════
#  Integration tests — QC API endpoints
# ══════════════════════════════════════════════════════════════════════════════


def _admin_headers(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_control(client, headers, analyte="Glucose", mean=5.0, sd=0.25):
    return client.post(
        "/api/v1/qc/controls",
        headers=headers,
        json={"analyte": analyte, "level": "Niveau 1", "unit": "mmol/L",
              "target_mean": mean, "target_sd": sd},
    )


class TestQcApi:

    def test_list_controls_requires_auth(self, client) -> None:
        assert client.get("/api/v1/qc/controls").status_code == 401

    def test_add_result_requires_auth(self, client) -> None:
        resp = client.post(
            "/api/v1/qc/results",
            json={"control_id": 1, "value": 5.0, "measured_at": "2026-06-01"},
        )
        assert resp.status_code == 401

    def test_create_control_unauthenticated_rejected(self, client) -> None:
        resp = client.post(
            "/api/v1/qc/controls",
            json={"analyte": "Test", "target_mean": 5.0, "target_sd": 0.3},
        )
        assert resp.status_code == 401

    def test_create_control_zero_sd_rejected(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/qc/controls",
            headers=headers,
            json={"analyte": "Test", "target_mean": 5.0, "target_sd": 0.0},
        )
        assert resp.status_code == 422

    def test_create_and_list_active_controls(self, client) -> None:
        headers = _admin_headers(client)
        resp = _make_control(client, headers, analyte="Hémoglobine", mean=140.0, sd=5.0)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["analyte"] == "Hémoglobine"
        assert data["is_active"] is True

        listed = client.get("/api/v1/qc/controls", headers=headers).json()
        assert any(c["analyte"] == "Hémoglobine" for c in listed)

    def test_add_result_in_control_no_violations(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = _make_control(client, headers, mean=7.0, sd=0.5).json()
        resp = client.post(
            "/api/v1/qc/results",
            headers=headers,
            json={"control_id": ctrl["id"], "value": 7.1, "measured_at": "2026-06-01"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["violations"] == []

    def test_add_result_triggers_1_3s(self, client) -> None:
        """z = (8.6 - 7.0) / 0.5 = 3.2 → 1-3s violation."""
        headers = _admin_headers(client)
        ctrl = _make_control(client, headers, analyte="WBC", mean=7.0, sd=0.5).json()
        resp = client.post(
            "/api/v1/qc/results",
            headers=headers,
            json={"control_id": ctrl["id"], "value": 8.6, "measured_at": "2026-06-02"},
        )
        assert resp.status_code == 201, resp.text
        assert "1-3s" in resp.json()["violations"]

    def test_add_result_unknown_control_returns_404(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/qc/results",
            headers=headers,
            json={"control_id": 99999, "value": 5.0, "measured_at": "2026-06-01"},
        )
        assert resp.status_code == 404

    def test_list_results_chronological_order(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = _make_control(client, headers, analyte="PLT", mean=250.0, sd=20.0).json()
        for val, dt in [(255, "2026-06-01"), (270, "2026-06-02"), (245, "2026-06-03")]:
            client.post(
                "/api/v1/qc/results",
                headers=headers,
                json={"control_id": ctrl["id"], "value": val, "measured_at": dt},
            )
        results = client.get(
            f"/api/v1/qc/controls/{ctrl['id']}/results", headers=headers
        ).json()
        assert len(results) == 3
        dates = [r["measured_at"] for r in results]
        assert dates == sorted(dates)

    def test_deactivate_control_removes_from_list(self, client) -> None:
        headers = _admin_headers(client)
        ctrl = _make_control(client, headers, analyte="RBC", mean=4.5, sd=0.3).json()

        del_resp = client.delete(
            f"/api/v1/qc/controls/{ctrl['id']}", headers=headers
        )
        assert del_resp.status_code == 200

        ids = [c["id"] for c in client.get(
            "/api/v1/qc/controls", headers=headers
        ).json()]
        assert ctrl["id"] not in ids

    def test_deactivate_unknown_control_returns_404(self, client) -> None:
        headers = _admin_headers(client)
        assert client.delete(
            "/api/v1/qc/controls/99999", headers=headers
        ).status_code == 404

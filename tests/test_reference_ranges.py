"""Tests — Valeurs de référence par analyte/sexe/âge (service + API + intégration)."""
import datetime as dt

from app.services.reference_checker import compute_flags

# ══════════════════════════════════════════════════════════════════════════════
#  Unit tests — compute_flags
# ══════════════════════════════════════════════════════════════════════════════


class _MockRange:
    def __init__(self, analyte, sex="*", age_min=None, age_max=None, lo=None, hi=None):
        self.analyte = analyte
        self.sex = sex
        self.age_min_years = age_min
        self.age_max_years = age_max
        self.low_normal = lo
        self.high_normal = hi
        self.is_active = True


class _MockDB:
    def __init__(self, ranges):
        self._ranges = ranges

    def query(self, model):
        return self

    def filter(self, *_):
        return self

    def all(self):
        return self._ranges


class TestComputeFlagsUnit:
    def test_no_ranges_returns_empty(self) -> None:
        db = _MockDB([])
        assert compute_flags({"HGB": 80.0}, "M", None, db) == {}

    def test_normal_flag(self) -> None:
        db = _MockDB([_MockRange("HGB", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 130.0}, "*", None, db)
        assert flags["HGB"] == "N"

    def test_high_flag(self) -> None:
        db = _MockDB([_MockRange("HGB", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 175.0}, "*", None, db)
        assert flags["HGB"] == "H"

    def test_very_high_flag(self) -> None:
        # > 160 * 1.30 = 208
        db = _MockDB([_MockRange("HGB", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 210.0}, "*", None, db)
        assert flags["HGB"] == "HH"

    def test_low_flag(self) -> None:
        db = _MockDB([_MockRange("HGB", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 100.0}, "*", None, db)
        assert flags["HGB"] == "L"

    def test_very_low_flag(self) -> None:
        # < 110 * 0.70 = 77
        db = _MockDB([_MockRange("HGB", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 70.0}, "*", None, db)
        assert flags["HGB"] == "LL"

    def test_sex_specific_beats_wildcard(self) -> None:
        ranges = [
            _MockRange("HGB", sex="*", lo=110.0, hi=160.0),
            _MockRange("HGB", sex="M", lo=130.0, hi=175.0),
        ]
        db = _MockDB(ranges)
        # Male patient with value 125 → L under male range, N under wildcard
        flags = compute_flags({"HGB": 125.0}, "M", None, db)
        assert flags["HGB"] == "L"

    def test_wrong_sex_excluded(self) -> None:
        db = _MockDB([_MockRange("HGB", sex="F", lo=110.0, hi=150.0)])
        # Male patient → female range excluded → no flag
        flags = compute_flags({"HGB": 80.0}, "M", None, db)
        assert "HGB" not in flags

    def test_age_filter_excludes_out_of_range(self) -> None:
        # Pédiatrique : 0–16 ans
        db = _MockDB([_MockRange("HGB", age_min=0, age_max=16, lo=110.0, hi=160.0)])
        adult_birth = dt.date.today() - dt.timedelta(days=365 * 35)
        flags = compute_flags({"HGB": 80.0}, "*", adult_birth, db)
        assert "HGB" not in flags

    def test_analyte_case_insensitive(self) -> None:
        db = _MockDB([_MockRange("hgb", lo=110.0, hi=160.0)])
        flags = compute_flags({"HGB": 80.0}, "*", None, db)
        # Matches because both are uppercased
        assert "HGB" in flags

    def test_unknown_analyte_no_flag(self) -> None:
        db = _MockDB([_MockRange("WBC", lo=4.0, hi=10.0)])
        flags = compute_flags({"PLT": 250.0}, "*", None, db)
        assert "PLT" not in flags

    def test_dict_value_extracted(self) -> None:
        db = _MockDB([_MockRange("WBC", lo=4.0, hi=10.0)])
        flags = compute_flags({"WBC": {"value": 12.0, "status": "H"}}, "*", None, db)
        assert flags["WBC"] == "H"


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _admin_headers(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_patient(client, headers, ipp: str, sex: str = "M",
                  birth: str = "1990-01-01") -> int:
    return client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "ipp_unique_id": ipp,
            "first_name": "Ref",
            "last_name": "Range",
            "birth_date": birth,
            "sex": sex,
        },
    ).json()["id"]


def _make_sample(client, headers, patient_id: int, barcode: str) -> int:
    return client.post(
        "/api/v1/samples",
        headers=headers,
        json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
    ).json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
#  API — reference ranges CRUD
# ══════════════════════════════════════════════════════════════════════════════


class TestReferenceRangeApi:

    def test_list_requires_auth(self, client) -> None:
        assert client.get("/api/v1/reference-ranges").status_code == 401

    def test_create_requires_officer(self, client) -> None:
        assert client.post(
            "/api/v1/reference-ranges",
            json={"analyte": "HGB", "low_normal": 110.0},
        ).status_code == 401

    def test_create_without_any_bound_rejected(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/reference-ranges",
            headers=headers,
            json={"analyte": "HGB"},
        )
        assert resp.status_code == 422

    def test_create_and_list(self, client) -> None:
        headers = _admin_headers(client)
        resp = client.post(
            "/api/v1/reference-ranges",
            headers=headers,
            json={"analyte": "HGB", "sex": "M", "low_normal": 130.0,
                  "high_normal": 175.0, "unit": "g/L"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["analyte"] == "HGB"
        assert data["low_normal"] == 130.0
        assert data["is_active"] is True

        listed = client.get("/api/v1/reference-ranges", headers=headers).json()
        assert any(r["analyte"] == "HGB" for r in listed)

    def test_deactivate_removes_from_list(self, client) -> None:
        headers = _admin_headers(client)
        rr = client.post("/api/v1/reference-ranges", headers=headers,
                         json={"analyte": "WBC", "low_normal": 4.0,
                               "high_normal": 10.0}).json()
        assert client.delete(
            f"/api/v1/reference-ranges/{rr['id']}", headers=headers
        ).status_code == 200
        ids = [r["id"] for r in client.get("/api/v1/reference-ranges", headers=headers).json()]
        assert rr["id"] not in ids

    def test_deactivate_unknown_returns_404(self, client) -> None:
        headers = _admin_headers(client)
        assert client.delete("/api/v1/reference-ranges/99999", headers=headers).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
#  Integration — flags auto-computed on result creation
# ══════════════════════════════════════════════════════════════════════════════


class TestReferenceFlagsIntegration:

    def test_high_flag_in_result(self, client) -> None:
        headers = _admin_headers(client)
        client.post("/api/v1/reference-ranges", headers=headers,
                    json={"analyte": "WBC", "low_normal": 4.0, "high_normal": 10.0})
        patient_id = _make_patient(client, headers, "IPP-RR-001")
        sample_id = _make_sample(client, headers, patient_id, "RR-S001")
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"WBC": 12.0},
                                   "is_critical": False}).json()
        assert result["flags"] is not None
        assert result["flags"].get("WBC") == "H"

    def test_very_high_flag_in_result(self, client) -> None:
        headers = _admin_headers(client)
        client.post("/api/v1/reference-ranges", headers=headers,
                    json={"analyte": "WBC", "low_normal": 4.0, "high_normal": 10.0})
        patient_id = _make_patient(client, headers, "IPP-RR-002")
        sample_id = _make_sample(client, headers, patient_id, "RR-S002")
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"WBC": 14.0},
                                   "is_critical": False}).json()
        assert result["flags"]["WBC"] == "HH"

    def test_low_flag_in_result(self, client) -> None:
        headers = _admin_headers(client)
        client.post("/api/v1/reference-ranges", headers=headers,
                    json={"analyte": "HGB", "low_normal": 120.0, "high_normal": 160.0})
        patient_id = _make_patient(client, headers, "IPP-RR-003")
        sample_id = _make_sample(client, headers, patient_id, "RR-S003")
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"HGB": 110.0},
                                   "is_critical": False}).json()
        assert result["flags"]["HGB"] == "L"

    def test_normal_flag_in_result(self, client) -> None:
        headers = _admin_headers(client)
        client.post("/api/v1/reference-ranges", headers=headers,
                    json={"analyte": "PLT", "low_normal": 150.0, "high_normal": 400.0})
        patient_id = _make_patient(client, headers, "IPP-RR-004")
        sample_id = _make_sample(client, headers, patient_id, "RR-S004")
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"PLT": 250.0},
                                   "is_critical": False}).json()
        assert result["flags"]["PLT"] == "N"

    def test_no_range_no_flag(self, client) -> None:
        """Analyte sans plage de référence → pas de flag."""
        headers = _admin_headers(client)
        patient_id = _make_patient(client, headers, "IPP-RR-005")
        sample_id = _make_sample(client, headers, patient_id, "RR-S005")
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"UNKNOWN": 99.0},
                                   "is_critical": False}).json()
        assert result["flags"] is None or "UNKNOWN" not in (result["flags"] or {})

    def test_sex_specific_range_male_patient(self, client) -> None:
        """Plage masculine appliquée correctement à un patient M."""
        headers = _admin_headers(client)
        client.post("/api/v1/reference-ranges", headers=headers,
                    json={"analyte": "HGB", "sex": "M",
                          "low_normal": 130.0, "high_normal": 175.0})
        patient_id = _make_patient(client, headers, "IPP-RR-006", sex="M",
                                   birth="1985-01-01")
        sample_id = _make_sample(client, headers, patient_id, "RR-S006")
        # 125 < 130 → L
        result = client.post("/api/v1/results", headers=headers,
                             json={"sample_id": sample_id,
                                   "data_points": {"HGB": 125.0},
                                   "is_critical": False}).json()
        assert result["flags"]["HGB"] == "L"

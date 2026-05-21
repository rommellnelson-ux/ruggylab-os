"""Unit tests for RuggyLab OS service layer.

These tests do not require a running database or HTTP server. They exercise
the pure business logic in the service and utility modules directly.
"""

import pytest

from app.services.malaria_ai import OfflineMalariaClassifier
from app.services.report_signing import report_hash
from app.services.validation.med_logic import (
    _build_overall_flags,
    _get_ranges,
    calculate_status,
    validate_nfs_parameters,
)

# ──────────────────────────────────────────────────────────────────────────────
# calculate_status
# ──────────────────────────────────────────────────────────────────────────────


def test_calculate_status_normal():
    assert calculate_status(7.5, 4.0, 10.0) == "N"


def test_calculate_status_low():
    assert calculate_status(3.9, 4.0, 10.0) == "L"


def test_calculate_status_high():
    assert calculate_status(11.0, 4.0, 10.0) == "H"


def test_calculate_status_at_boundaries():
    # Boundary values are inclusive for normal range
    assert calculate_status(4.0, 4.0, 10.0) == "N"
    assert calculate_status(10.0, 4.0, 10.0) == "N"


# ──────────────────────────────────────────────────────────────────────────────
# _get_ranges — paediatric / adult reference ranges
# ──────────────────────────────────────────────────────────────────────────────


class TestGetRanges:
    """Verify that _get_ranges returns sensible reference values for each
    age group, and that sex-differentiation works for adults."""

    def test_neonate_has_wider_wbc_range(self):
        r = _get_ranges(0.5, "M")
        # Neonates normally have higher WBC upper limit than adults
        assert r.wbc_high > 14.0

    def test_toddler_1_to_5(self):
        r = _get_ranges(3.0, "F")
        assert r.wbc_low == 5.0
        assert r.wbc_high == 15.0

    def test_child_6_to_11(self):
        r = _get_ranges(8.0, "M")
        assert r.wbc_low == 4.5
        assert r.hgb_low == 115.0

    def test_adolescent_sex_differentiation(self):
        r_m = _get_ranges(15.0, "M")
        r_f = _get_ranges(15.0, "F")
        assert r_m.hgb_low > r_f.hgb_low

    def test_adult_male_higher_hgb_than_female(self):
        r_m = _get_ranges(30.0, "M")
        r_f = _get_ranges(30.0, "F")
        assert r_m.hgb_low == 130.0
        assert r_f.hgb_low == 120.0
        assert r_m.hgb_high == 170.0
        assert r_f.hgb_high == 150.0

    def test_adult_male_hct_range(self):
        r = _get_ranges(25.0, "M")
        assert r.hct_low == 40.0
        assert r.hct_high == 54.0

    def test_unknown_sex_uses_female_defaults(self):
        # sex=None — should not raise; use lower (female) defaults
        r = _get_ranges(25.0, None)
        assert r.hgb_low == 120.0


# ──────────────────────────────────────────────────────────────────────────────
# validate_nfs_parameters
# ──────────────────────────────────────────────────────────────────────────────


_NORMAL_ADULT_RAW: dict[str, float] = {
    "WBC": 6.5,
    "RBC": 4.8,
    "HGB": 145.0,
    "HCT": 43.0,
    "MCV": 88.0,
    "MCH": 30.0,
    "MCHC": 335.0,
    "PLT": 280.0,
}


class TestValidateNFSParameters:
    def test_normal_adult_male_no_panic(self):
        validated, is_panic = validate_nfs_parameters(_NORMAL_ADULT_RAW, 35, "M")
        assert not is_panic
        assert validated.WBC.status == "N"
        assert validated.HGB.status == "N"

    def test_critical_low_wbc_triggers_panic(self):
        raw = {**_NORMAL_ADULT_RAW, "WBC": 1.5}
        _, is_panic = validate_nfs_parameters(raw, 35, "M")
        assert is_panic

    def test_critical_high_wbc_triggers_panic(self):
        raw = {**_NORMAL_ADULT_RAW, "WBC": 22.0}
        _, is_panic = validate_nfs_parameters(raw, 35, "M")
        assert is_panic

    def test_critical_low_hgb_triggers_panic(self):
        raw = {**_NORMAL_ADULT_RAW, "HGB": 60.0}
        _, is_panic = validate_nfs_parameters(raw, 35, "M")
        assert is_panic

    def test_critical_low_plt_triggers_panic(self):
        raw = {**_NORMAL_ADULT_RAW, "PLT": 20.0}
        _, is_panic = validate_nfs_parameters(raw, 35, "F")
        assert is_panic

    def test_low_hgb_adult_female_flagged_l(self):
        raw = {**_NORMAL_ADULT_RAW, "HGB": 115.0}
        validated, _ = validate_nfs_parameters(raw, 35, "F")
        assert validated.HGB.status == "L"

    def test_paediatric_ranges_applied_for_child(self):
        # Child 8y: WBC upper limit is 13.5, not 10.0 (adult)
        raw = {**_NORMAL_ADULT_RAW, "WBC": 12.0}
        validated_adult, _ = validate_nfs_parameters(raw, 35, "M")
        validated_child, _ = validate_nfs_parameters(raw, 8, "M")
        assert validated_adult.WBC.status == "H"   # out of adult range
        assert validated_child.WBC.status == "N"   # within child range

    def test_overall_flags_populated(self):
        raw = {**_NORMAL_ADULT_RAW, "HGB": 110.0}  # low HGB → ANEMIE
        validated, _ = validate_nfs_parameters(raw, 35, "F")
        assert "ANEMIE" in validated.overall_flags

    def test_calibration_stores_equipment_serial(self):
        validated, _ = validate_nfs_parameters(_NORMAL_ADULT_RAW, 35, "M", "DH36-001")
        assert validated.calibration.equipment_serial == "DH36-001"
        assert validated.calibration.validated is True


# ──────────────────────────────────────────────────────────────────────────────
# _build_overall_flags
# ──────────────────────────────────────────────────────────────────────────────


def _make_points(**overrides):
    """Build a minimal points dict with normal statuses, then apply overrides."""
    from app.schemas.dh36_interfacing import RuggylabJSONPoint

    defaults = {
        "WBC": RuggylabJSONPoint(value=6.0, unit="10*9/L", status="N", is_critical=False),
        "RBC": RuggylabJSONPoint(value=4.5, unit="10*12/L", status="N", is_critical=False),
        "HGB": RuggylabJSONPoint(value=140.0, unit="g/L", status="N", is_critical=False),
        "HCT": RuggylabJSONPoint(value=42.0, unit="%", status="N", is_critical=False),
        "MCV": RuggylabJSONPoint(value=88.0, unit="fL", status="N", is_critical=False),
        "MCH": RuggylabJSONPoint(value=30.0, unit="pg", status="N", is_critical=False),
        "MCHC": RuggylabJSONPoint(value=335.0, unit="g/L", status="N", is_critical=False),
        "PLT": RuggylabJSONPoint(value=280.0, unit="10*9/L", status="N", is_critical=False),
    }
    defaults.update(overrides)
    return defaults


class TestBuildOverallFlags:
    def test_no_flags_when_all_normal(self):
        assert _build_overall_flags(_make_points()) == []

    def test_anemie_when_hgb_low(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            HGB=RuggylabJSONPoint(value=110.0, unit="g/L", status="L", is_critical=False)
        )
        flags = _build_overall_flags(pts)
        assert "ANEMIE" in flags
        assert "ANEMIE_SEVERE" not in flags

    def test_anemie_severe_when_hgb_critical(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            HGB=RuggylabJSONPoint(value=55.0, unit="g/L", status="L", is_critical=True)
        )
        flags = _build_overall_flags(pts)
        assert "ANEMIE_SEVERE" in flags
        assert "ANEMIE" not in flags  # severe replaces simple

    def test_thrombopenie_severe_when_plt_critical(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            PLT=RuggylabJSONPoint(value=20.0, unit="10*9/L", status="L", is_critical=True)
        )
        flags = _build_overall_flags(pts)
        assert "THROMBOPENIE_SEVERE" in flags
        assert "THROMBOPENIE" not in flags

    def test_hyperleucocytose(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            WBC=RuggylabJSONPoint(value=14.0, unit="10*9/L", status="H", is_critical=False)
        )
        assert "HYPERLEUCOCYTOSE" in _build_overall_flags(pts)

    def test_microcytose(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            MCV=RuggylabJSONPoint(value=70.0, unit="fL", status="L", is_critical=False)
        )
        assert "MICROCYTOSE" in _build_overall_flags(pts)

    def test_pantopenique_replaces_individual_flags(self):
        from app.schemas.dh36_interfacing import RuggylabJSONPoint

        pts = _make_points(
            WBC=RuggylabJSONPoint(value=1.8, unit="10*9/L", status="L", is_critical=False),
            HGB=RuggylabJSONPoint(value=80.0, unit="g/L", status="L", is_critical=False),
            PLT=RuggylabJSONPoint(value=80.0, unit="10*9/L", status="L", is_critical=False),
        )
        flags = _build_overall_flags(pts)
        assert "PANTOPENIQUE" in flags
        assert "LEUCOPENIE" not in flags
        assert "ANEMIE" not in flags
        assert "THROMBOPENIE" not in flags


# ──────────────────────────────────────────────────────────────────────────────
# OfflineMalariaClassifier
# ──────────────────────────────────────────────────────────────────────────────


class TestOfflineMalariaClassifier:
    classifier = OfflineMalariaClassifier("models/fake")

    def test_positive_keyword_in_url(self):
        pred = self.classifier.predict("data/microscopy/sample_positive.tiff")
        assert pred.label == "positive"
        assert 0.8 <= pred.confidence <= 1.0

    def test_palud_keyword(self):
        pred = self.classifier.predict("data/microscopy/palud_001.tiff")
        assert pred.label == "positive"

    def test_negative_keyword(self):
        pred = self.classifier.predict("data/microscopy/negative_ctrl.tiff")
        assert pred.label == "negative"

    def test_deterministic_for_same_url(self):
        url = "data/microscopy/unknown_sample_xyz.tiff"
        pred1 = self.classifier.predict(url)
        pred2 = self.classifier.predict(url)
        assert pred1.label == pred2.label
        assert pred1.confidence == pred2.confidence

    def test_confidence_in_valid_range(self):
        for url in [
            "data/abc.tiff",
            "data/def.tiff",
            "data/ghi.tiff",
        ]:
            pred = self.classifier.predict(url)
            assert 0.0 <= pred.confidence <= 1.0
            assert pred.label in ("positive", "negative")


# ──────────────────────────────────────────────────────────────────────────────
# DH36Parser
# ──────────────────────────────────────────────────────────────────────────────

_SAMPLE_HL7 = (
    "MSH|^~\\&|DH36|LAB|LIS|LAB|20260501120000||ORU^R01|MSG001|P|2.3\r"
    "PID|||IPP-001^^^LAB^PI||Doe^John||19850315|M\r"
    "OBR|1||SAMPLE-001^LAB|||20260501120000\r"
    "OBX|1|NM|WBC^WBC||6.5|10*9/L|4.0-10.0|N|||F\r"
    "OBX|2|NM|HGB^HGB||145.0|g/L|130-170|N|||F\r"
    "OBX|3|NM|PLT^PLT||280.0|10*9/L|150-450|N|||F\r"
)


class TestDH36Parser:
    def test_get_info_extracts_fields(self):
        from app.services.interfacing.dymind_dh36 import DH36Parser

        parser = DH36Parser(_SAMPLE_HL7)
        info = parser.get_info()
        assert info["ipp"] == "IPP-001"
        assert info["barcode"] == "SAMPLE-001"
        assert info["message_control_id"] == "MSG001"

    def test_parse_results_returns_mapped_parameters(self):
        from app.services.interfacing.dymind_dh36 import DH36Parser

        parser = DH36Parser(_SAMPLE_HL7)
        results = parser.parse_results()
        assert "WBC" in results
        assert results["WBC"] == pytest.approx(6.5)
        assert "HGB" in results
        assert results["HGB"] == pytest.approx(145.0)
        assert "PLT" in results

    def test_parse_results_ignores_unknown_parameters(self):
        from app.services.interfacing.dymind_dh36 import DH36Parser

        hl7_extra = _SAMPLE_HL7 + "OBX|4|NM|UNKNOWN^UNKNOWN||99.0|?|||F\r"
        parser = DH36Parser(hl7_extra)
        results = parser.parse_results()
        assert "UNKNOWN" not in results

    def test_invalid_hl7_raises_value_error(self):
        from app.services.interfacing.dymind_dh36 import DH36Parser

        with pytest.raises(ValueError, match="HL7"):
            DH36Parser("NOT A VALID HL7 MESSAGE AT ALL @@@")


# ──────────────────────────────────────────────────────────────────────────────
# report_hash — determinism and sensitivity to data changes
# ──────────────────────────────────────────────────────────────────────────────


class TestReportHash:
    def _mock_result(self, **overrides):
        """Build a minimal mock Result-like object for hashing tests."""
        from unittest.mock import MagicMock

        result = MagicMock()
        result.id = overrides.get("id", 1)
        result.sample_id = overrides.get("sample_id", 10)
        result.equipment_id = overrides.get("equipment_id", 5)
        result.analysis_date.isoformat.return_value = "2026-05-01T12:00:00"
        result.data_points = overrides.get("data_points", {"WBC": 6.5})
        result.is_critical = overrides.get("is_critical", False)
        result.is_validated = overrides.get("is_validated", True)
        result.validator_id = overrides.get("validator_id", 1)

        sample = MagicMock()
        sample.barcode = "SAMPLE-001"
        patient = MagicMock()
        patient.ipp_unique_id = "IPP-001"
        patient.first_name = "Jean"
        patient.last_name = "Dupont"
        patient.birth_date.isoformat.return_value = "1985-03-15"
        patient.sex = "M"
        sample.patient = patient
        result.sample = sample

        equipment = MagicMock()
        equipment.name = "Dymind DH36"
        equipment.serial_number = "DH36-001"
        result.equipment = equipment

        return result

    def test_hash_is_deterministic(self):
        r = self._mock_result()
        h1 = report_hash(r)
        h2 = report_hash(r)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_changes_when_data_changes(self):
        r1 = self._mock_result(data_points={"WBC": 6.5})
        r2 = self._mock_result(data_points={"WBC": 99.9})
        assert report_hash(r1) != report_hash(r2)

    def test_hash_changes_when_critical_flag_changes(self):
        r1 = self._mock_result(is_critical=False)
        r2 = self._mock_result(is_critical=True)
        assert report_hash(r1) != report_hash(r2)

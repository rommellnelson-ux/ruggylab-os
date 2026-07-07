from dataclasses import dataclass

from app.schemas.dh36_interfacing import (
    CalibrationFlag,
    HematologyDataDH36JSONB,
    RuggylabJSONPoint,
)


def calculate_status(value: float, low: float, high: float) -> str:
    if value < low:
        return "L"
    if value > high:
        return "H"
    return "N"


def _build_point(
    *,
    value: float,
    unit: str,
    low: float,
    high: float,
    critical_low: float | None = None,
    critical_high: float | None = None,
) -> RuggylabJSONPoint:
    is_critical = False
    if critical_low is not None and value <= critical_low:
        is_critical = True
    if critical_high is not None and value >= critical_high:
        is_critical = True

    return RuggylabJSONPoint(
        value=value,
        unit=unit,
        status=calculate_status(value, low, high),
        ref_range=f"{low}-{high}",
        is_critical=is_critical,
    )


@dataclass(frozen=True)
class _NFSRanges:
    """Reference ranges for a single NFS parameter."""

    wbc_low: float
    wbc_high: float
    wbc_critical_low: float
    wbc_critical_high: float
    rbc_low: float
    rbc_high: float
    hgb_low: float
    hgb_high: float
    hgb_critical_low: float
    hct_low: float
    hct_high: float
    mcv_low: float
    mcv_high: float
    mch_low: float
    mch_high: float
    mchc_low: float
    mchc_high: float
    plt_low: float
    plt_high: float
    plt_critical_low: float


def _get_ranges(age: float, sex: str | None) -> _NFSRanges:
    """Return age- and sex-adapted NFS reference ranges.

    Sources: WHO, Société Française de Biologie Clinique (SFBC) paediatric tables.
    Age thresholds (years):
      < 1   → nourrisson
      1–5   → enfant en bas âge
      6–11  → enfant scolarisé
      12–17 → adolescent
      ≥ 18  → adulte
    """
    is_male = sex == "M"

    if age < 1:
        # Nourrisson (valeurs moyennes 2–12 mois)
        return _NFSRanges(
            wbc_low=6.0,
            wbc_high=17.5,
            wbc_critical_low=2.0,
            wbc_critical_high=30.0,
            rbc_low=3.7,
            rbc_high=5.3,
            hgb_low=100.0,
            hgb_high=140.0,
            hgb_critical_low=70.0,
            hct_low=33.0,
            hct_high=42.0,
            mcv_low=70.0,
            mcv_high=84.0,
            mch_low=23.0,
            mch_high=31.0,
            mchc_low=300.0,
            mchc_high=360.0,
            plt_low=200.0,
            plt_high=550.0,
            plt_critical_low=30.0,
        )
    if age < 6:
        # Enfant 1–5 ans
        return _NFSRanges(
            wbc_low=5.0,
            wbc_high=15.0,
            wbc_critical_low=2.0,
            wbc_critical_high=25.0,
            rbc_low=3.9,
            rbc_high=5.0,
            hgb_low=110.0,
            hgb_high=140.0,
            hgb_critical_low=70.0,
            hct_low=34.0,
            hct_high=40.0,
            mcv_low=75.0,
            mcv_high=87.0,
            mch_low=24.0,
            mch_high=30.0,
            mchc_low=310.0,
            mchc_high=360.0,
            plt_low=150.0,
            plt_high=450.0,
            plt_critical_low=30.0,
        )
    if age < 12:
        # Enfant 6–11 ans
        return _NFSRanges(
            wbc_low=4.5,
            wbc_high=13.5,
            wbc_critical_low=2.0,
            wbc_critical_high=25.0,
            rbc_low=4.0,
            rbc_high=5.2,
            hgb_low=115.0,
            hgb_high=145.0,
            hgb_critical_low=70.0,
            hct_low=35.0,
            hct_high=44.0,
            mcv_low=77.0,
            mcv_high=91.0,
            mch_low=25.0,
            mch_high=31.0,
            mchc_low=310.0,
            mchc_high=360.0,
            plt_low=150.0,
            plt_high=450.0,
            plt_critical_low=30.0,
        )
    if age < 18:
        # Adolescent 12–17 ans
        hgb_low = 130.0 if is_male else 120.0
        hgb_high = 160.0 if is_male else 150.0
        return _NFSRanges(
            wbc_low=4.5,
            wbc_high=13.0,
            wbc_critical_low=2.0,
            wbc_critical_high=20.0,
            rbc_low=4.2 if is_male else 3.9,
            rbc_high=5.6 if is_male else 5.2,
            hgb_low=hgb_low,
            hgb_high=hgb_high,
            hgb_critical_low=70.0,
            hct_low=37.0 if is_male else 35.0,
            hct_high=50.0 if is_male else 45.0,
            mcv_low=80.0,
            mcv_high=96.0,
            mch_low=26.0,
            mch_high=34.0,
            mchc_low=310.0,
            mchc_high=360.0,
            plt_low=150.0,
            plt_high=450.0,
            plt_critical_low=30.0,
        )

    # Adulte ≥ 18 ans
    hgb_low = 130.0 if is_male else 120.0
    hgb_high = 170.0 if is_male else 150.0
    return _NFSRanges(
        wbc_low=4.0,
        wbc_high=10.0,
        wbc_critical_low=2.0,
        wbc_critical_high=20.0,
        rbc_low=4.5 if is_male else 3.8,
        rbc_high=5.9 if is_male else 5.2,
        hgb_low=hgb_low,
        hgb_high=hgb_high,
        hgb_critical_low=70.0,
        hct_low=40.0 if is_male else 36.0,
        hct_high=54.0 if is_male else 48.0,
        mcv_low=82.0,
        mcv_high=98.0,
        mch_low=27.0,
        mch_high=34.0,
        mchc_low=310.0,
        mchc_high=360.0,
        plt_low=150.0,
        plt_high=450.0,
        plt_critical_low=30.0,
    )


def validate_nfs_parameters(
    results_raw: dict[str, float],
    patient_age: float,
    patient_sex: str | None,
    equipment_serial: str | None = None,
) -> tuple[HematologyDataDH36JSONB, bool]:
    r = _get_ranges(patient_age, patient_sex)

    points = {
        "WBC": _build_point(
            value=results_raw.get("WBC", 0.0),
            unit="10*9/L",
            low=r.wbc_low,
            high=r.wbc_high,
            critical_low=r.wbc_critical_low,
            critical_high=r.wbc_critical_high,
        ),
        "RBC": _build_point(
            value=results_raw.get("RBC", 0.0),
            unit="10*12/L",
            low=r.rbc_low,
            high=r.rbc_high,
        ),
        "HGB": _build_point(
            value=results_raw.get("HGB", 0.0),
            unit="g/L",
            low=r.hgb_low,
            high=r.hgb_high,
            critical_low=r.hgb_critical_low,
        ),
        "HCT": _build_point(
            value=results_raw.get("HCT", 0.0),
            unit="%",
            low=r.hct_low,
            high=r.hct_high,
        ),
        "MCV": _build_point(
            value=results_raw.get("MCV", 0.0),
            unit="fL",
            low=r.mcv_low,
            high=r.mcv_high,
        ),
        "MCH": _build_point(
            value=results_raw.get("MCH", 0.0),
            unit="pg",
            low=r.mch_low,
            high=r.mch_high,
        ),
        "MCHC": _build_point(
            value=results_raw.get("MCHC", 0.0),
            unit="g/L",
            low=r.mchc_low,
            high=r.mchc_high,
        ),
        "PLT": _build_point(
            value=results_raw.get("PLT", 0.0),
            unit="10*9/L",
            low=r.plt_low,
            high=r.plt_high,
            critical_low=r.plt_critical_low,
        ),
    }

    is_panic = any(point.is_critical for point in points.values())
    overall_flags = _build_overall_flags(points)
    validated = HematologyDataDH36JSONB(
        **points,
        calibration=CalibrationFlag(validated=True, equipment_serial=equipment_serial),
        overall_flags=overall_flags,
    )
    return validated, is_panic


def _build_overall_flags(points: dict[str, RuggylabJSONPoint]) -> list[str]:
    """Derive clinical interpretation flags from individual parameter statuses.

    These flags synthesise cross-parameter patterns that a single parameter
    status cannot capture (e.g. pancytopenia requires WBC + HGB + PLT all low).
    Terms are intentionally in French to match the rest of the clinical output.
    """
    flags: list[str] = []

    wbc = points.get("WBC")
    hgb = points.get("HGB")
    plt = points.get("PLT")
    mcv = points.get("MCV")
    rbc = points.get("RBC")

    # Anaemia
    if hgb and hgb.is_critical:
        flags.append("ANEMIE_SEVERE")
    elif hgb and hgb.status == "L":
        flags.append("ANEMIE")

    # Polycythaemia
    if rbc and rbc.status == "H":
        flags.append("POLYGLOBULIE")

    # White cell count anomalies
    if wbc and wbc.status == "L":
        flags.append("LEUCOPENIE")
    elif wbc and wbc.status == "H":
        flags.append("HYPERLEUCOCYTOSE")

    # Platelet anomalies
    if plt and plt.is_critical:
        flags.append("THROMBOPENIE_SEVERE")
    elif plt and plt.status == "L":
        flags.append("THROMBOPENIE")

    # MCV-based morphology
    if mcv and mcv.status == "L":
        flags.append("MICROCYTOSE")
    elif mcv and mcv.status == "H":
        flags.append("MACROCYTOSE")

    # Pancytopenia (all three cell lines low)
    if wbc and wbc.status == "L" and hgb and hgb.status == "L" and plt and plt.status == "L":
        # Replace the three individual flags with the synthetic one
        for flag in ("LEUCOPENIE", "ANEMIE", "THROMBOPENIE"):
            if flag in flags:
                flags.remove(flag)
        flags.insert(0, "PANTOPENIQUE")

    return flags

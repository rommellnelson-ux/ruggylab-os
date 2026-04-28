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
    if critical_low is not None and value < critical_low:
        is_critical = True
    if critical_high is not None and value > critical_high:
        is_critical = True

    return RuggylabJSONPoint(
        value=value,
        unit=unit,
        status=calculate_status(value, low, high),
        ref_range=f"{low}-{high}",
        is_critical=is_critical,
    )


def validate_nfs_parameters(
    results_raw: dict[str, float],
    patient_age: float,
    patient_sex: str | None,
    equipment_serial: str | None = None,
) -> tuple[HematologyDataDH36JSONB, bool]:
    del patient_age

    hgb_low, hgb_high = (130.0, 170.0) if patient_sex == "M" else (120.0, 150.0)

    points = {
        "WBC": _build_point(
            value=results_raw.get("WBC", 0.0),
            unit="10*9/L",
            low=4.0,
            high=10.0,
            critical_low=2.0,
            critical_high=20.0,
        ),
        "RBC": _build_point(
            value=results_raw.get("RBC", 0.0),
            unit="10*12/L",
            low=3.5,
            high=5.5,
        ),
        "HGB": _build_point(
            value=results_raw.get("HGB", 0.0),
            unit="g/L",
            low=hgb_low,
            high=hgb_high,
            critical_low=70.0,
        ),
        "HCT": _build_point(
            value=results_raw.get("HCT", 0.0),
            unit="%",
            low=37.0,
            high=50.0,
        ),
        "MCV": _build_point(
            value=results_raw.get("MCV", 0.0),
            unit="fL",
            low=82.0,
            high=98.0,
        ),
        "MCH": _build_point(
            value=results_raw.get("MCH", 0.0),
            unit="pg",
            low=27.0,
            high=34.0,
        ),
        "MCHC": _build_point(
            value=results_raw.get("MCHC", 0.0),
            unit="g/L",
            low=310.0,
            high=360.0,
        ),
        "PLT": _build_point(
            value=results_raw.get("PLT", 0.0),
            unit="10*9/L",
            low=150.0,
            high=450.0,
            critical_low=30.0,
        ),
    }

    is_panic = any(point.is_critical for point in points.values())
    validated = HematologyDataDH36JSONB(
        **points,
        calibration=CalibrationFlag(validated=True, equipment_serial=equipment_serial),
        overall_flags=[],
    )
    return validated, is_panic

from app.schemas.precis_expert import PrecisExpertManualInput
from app.services.validation.precis_expert import (
    PrecisExpertValidator,
    calculate_status,
)


def test_glucose_panic_thresholds() -> None:
    mock_input = PrecisExpertManualInput(
        sample_barcode="VMA2026-001",
        equipment_serial="PE-98765",
        glucose_raw=0.45,
        glucose_unit="g/L",
        cholesterol_raw=1.8,
        cholesterol_unit="g/L",
        uric_acid_raw=50.0,
        uric_acid_unit="mg/L",
        lactate_raw=1.2,
        lactate_unit="mmol/L",
        ketones_raw=0.2,
        ketones_unit="mmol/L",
    )

    validator = PrecisExpertValidator(
        mock_input, patient_age=35, patient_sex="M", user_id=1
    )
    validated_jsonb, is_panic = validator.validate_all()

    assert is_panic is True
    assert validated_jsonb.GLU.status == "L"
    assert validated_jsonb.GLU.is_critical is True
    assert validated_jsonb.manual_entry_by == 1


def test_uric_acid_gender_differentiation() -> None:
    input_val = 65.0

    status_m = calculate_status(input_val, 35, 72)
    status_f = calculate_status(input_val, 26, 60)

    assert status_m == "N"
    assert status_f == "H"


def test_lactate_critical_threshold() -> None:
    mock_input = PrecisExpertManualInput(
        sample_barcode="VMA2026-002",
        equipment_serial="PE-12345",
        glucose_raw=0.95,
        cholesterol_raw=1.7,
        uric_acid_raw=42.0,
        lactate_raw=4.5,
        ketones_raw=0.3,
    )

    validator = PrecisExpertValidator(
        mock_input, patient_age=29, patient_sex="F", user_id=7
    )
    validated_jsonb, is_panic = validator.validate_all()

    assert is_panic is True
    assert validated_jsonb.LAC.status == "H"
    assert validated_jsonb.LAC.is_critical is True

from app.services.validation.med_logic import calculate_status, validate_nfs_parameters


def test_calculate_status_returns_normal_within_range() -> None:
    assert calculate_status(5.0, 4.0, 10.0) == "N"


def test_validate_nfs_parameters_marks_critical_hgb() -> None:
    payload, is_panic = validate_nfs_parameters(
        {
            "WBC": 8.0,
            "RBC": 4.6,
            "HGB": 60.0,
            "HCT": 40.0,
            "MCV": 87.0,
            "MCH": 30.0,
            "MCHC": 330.0,
            "PLT": 220.0,
        },
        patient_age=35,
        patient_sex="M",
        equipment_serial="DH36-001",
    )

    assert is_panic is True
    assert payload.HGB.status == "L"
    assert payload.HGB.is_critical is True
    assert payload.calibration.equipment_serial == "DH36-001"


def test_validate_nfs_parameters_marks_critical_wbc() -> None:
    payload, is_panic = validate_nfs_parameters(
        {
            "WBC": 25.0,
            "RBC": 4.2,
            "HGB": 140.0,
            "HCT": 41.0,
            "MCV": 90.0,
            "MCH": 31.0,
            "MCHC": 340.0,
            "PLT": 200.0,
        },
        patient_age=28,
        patient_sex="F",
    )

    assert is_panic is True
    assert payload.WBC.status == "H"
    assert payload.WBC.is_critical is True

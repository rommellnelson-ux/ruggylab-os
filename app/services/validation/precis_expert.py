import datetime as dt

from app.schemas.dh36_interfacing import RuggylabJSONPoint
from app.schemas.precis_expert import PrecisExpertJSONB, PrecisExpertManualInput


def utcnow_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def calculate_status(value: float, low: float, high: float) -> str:
    if value < low:
        return "L"
    if value > high:
        return "H"
    return "N"


class PrecisExpertValidator:
    def __init__(self, input_data: PrecisExpertManualInput, patient_age: float, patient_sex: str | None, user_id: int):
        self.input = input_data
        self.patient_age = patient_age
        self.patient_sex = patient_sex
        self.user_id = user_id
        self.is_overall_critical = False

    def _point(
        self,
        *,
        value: float,
        unit: str,
        low: float,
        high: float,
        critical_low: float | None = None,
        critical_high: float | None = None,
    ) -> RuggylabJSONPoint:
        status = calculate_status(value, low, high)
        is_critical = False
        if critical_low is not None and value < critical_low:
            is_critical = True
        if critical_high is not None and value > critical_high:
            is_critical = True
        if is_critical:
            self.is_overall_critical = True
        return RuggylabJSONPoint(
            value=value,
            unit=unit,
            status=status,
            ref_range=f"{low}-{high}",
            is_critical=is_critical,
        )

    def validate_all(self) -> tuple[PrecisExpertJSONB, bool]:
        point_glu = self._point(
            value=self.input.glucose_raw,
            unit=self.input.glucose_unit,
            low=0.7,
            high=1.10,
            critical_low=0.50,
            critical_high=3.0,
        )
        point_chol = self._point(
            value=self.input.cholesterol_raw,
            unit=self.input.cholesterol_unit,
            low=1.4,
            high=2.0,
        )
        ua_low, ua_high = (35.0, 72.0) if self.patient_sex == "M" else (26.0, 60.0)
        point_ua = self._point(
            value=self.input.uric_acid_raw,
            unit=self.input.uric_acid_unit,
            low=ua_low,
            high=ua_high,
        )
        point_lac = self._point(
            value=self.input.lactate_raw,
            unit=self.input.lactate_unit,
            low=0.5,
            high=2.2,
            critical_high=4.0,
        )
        point_ket = self._point(
            value=self.input.ketones_raw,
            unit=self.input.ketones_unit,
            low=0.0,
            high=0.6,
        )

        return (
            PrecisExpertJSONB(
                GLU=point_glu,
                CHOL=point_chol,
                UA=point_ua,
                LAC=point_lac,
                KET=point_ket,
                manual_entry_by=self.user_id,
                entry_timestamp=utcnow_iso(),
            ),
            self.is_overall_critical,
        )

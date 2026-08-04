"""Validateur historique de l'appareil POCT Precis Expert.

Conserve son API publique (utilisée par ``/results/precis-expert``), mais
délègue désormais les bornes cliniques au catalogue partagé
``poct_reference`` — source unique également consommée par la route générique
``/results/poct-batch``.
"""

import datetime as dt

from app.schemas.dh36_interfacing import RuggylabJSONPoint
from app.schemas.precis_expert import PrecisExpertJSONB, PrecisExpertManualInput
from app.services.validation.poct_reference import build_poct_point, calculate_status

__all__ = ["PrecisExpertValidator", "calculate_status", "utcnow_iso"]


def utcnow_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class PrecisExpertValidator:
    def __init__(
        self,
        input_data: PrecisExpertManualInput,
        patient_age: float,
        patient_sex: str | None,
        user_id: int,
    ):
        self.input = input_data
        self.patient_age = patient_age
        self.patient_sex = patient_sex
        self.user_id = user_id
        self.is_overall_critical = False

    def _point(self, code: str, value: float, unit: str) -> RuggylabJSONPoint:
        point = build_poct_point(code, value, unit, self.patient_sex)
        if point.is_critical:
            self.is_overall_critical = True
        return point

    def validate_all(self) -> tuple[PrecisExpertJSONB, bool]:
        return (
            PrecisExpertJSONB(
                GLU=self._point("GLU", self.input.glucose_raw, self.input.glucose_unit),
                CHOL=self._point("CHOL", self.input.cholesterol_raw, self.input.cholesterol_unit),
                UA=self._point("UA", self.input.uric_acid_raw, self.input.uric_acid_unit),
                LAC=self._point("LAC", self.input.lactate_raw, self.input.lactate_unit),
                KET=self._point("KET", self.input.ketones_raw, self.input.ketones_unit),
                manual_entry_by=self.user_id,
                entry_timestamp=utcnow_iso(),
            ),
            self.is_overall_critical,
        )

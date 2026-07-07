"""Unités canoniques de laboratoire et conversions sûres.

Les codes retournés sont des codes UCUM. Une conversion n'est effectuée que
pour des unités explicitement compatibles ; sinon la valeur reste inchangée et
le moteur d'interprétation signale que l'unité n'a pas pu être rapprochée.
"""

from __future__ import annotations

import re


def _key(unit: str | None) -> str:
    if not unit:
        return ""
    return re.sub(r"\s+", "", unit).replace("×", "x").replace("µ", "u").lower()


_ALIASES = {
    "g/l": "g/L",
    "g/dl": "g/dL",
    "mg/l": "mg/L",
    "mg/dl": "mg/dL",
    "mmol/l": "mmol/L",
    "umol/l": "umol/L",
    "ui/l": "[IU]/L",
    "iu/l": "[IU]/L",
    "[iu]/l": "[IU]/L",
    "%": "%",
    "fl": "fL",
    "pg": "pg",
    "ml": "mL",
    "t/l": "10*12/L",
    "10*12/l": "10*12/L",
    "10^12/l": "10*12/L",
    "10x12/l": "10*12/L",
    "g/l_cells": "10*9/L",
    "10*9/l": "10*9/L",
    "10^9/l": "10*9/L",
    "10x9/l": "10*9/L",
    "10*3/ul": "10*9/L",
    "10^3/ul": "10*9/L",
    "10*6/ul": "10*12/L",
    "10^6/ul": "10*12/L",
    "ml/min/1,73m2": "mL/min/{1.73_m2}",
    "ml/min/1.73m2": "mL/min/{1.73_m2}",
    "ml/min/1,73m²": "mL/min/{1.73_m2}",
}


def canonical_unit(unit: str | None) -> str | None:
    """Normalise un libellé d'unité vers un code UCUM connu."""
    if unit is None:
        return None
    stripped = unit.strip()
    if not stripped:
        return ""
    return _ALIASES.get(_key(stripped), stripped)


_LINEAR_FACTORS: dict[tuple[str, str], float] = {
    ("g/dL", "g/L"): 10.0,
    ("g/L", "g/dL"): 0.1,
    ("mg/dL", "mg/L"): 10.0,
    ("mg/L", "mg/dL"): 0.1,
    ("mg/L", "g/L"): 0.001,
    ("g/L", "mg/L"): 1000.0,
    ("umol/L", "mmol/L"): 0.001,
    ("mmol/L", "umol/L"): 1000.0,
}


def convert_value(value: float, source_unit: str | None, target_unit: str | None) -> tuple[float, bool]:
    """Convertit ``value`` vers ``target_unit``.

    Retourne ``(valeur, unité_compatible)``. Une unité absente signifie que la
    valeur est déjà exprimée dans l'unité canonique attendue.
    """
    source = canonical_unit(source_unit)
    target = canonical_unit(target_unit)
    if not source or not target or source == target:
        return value, True
    factor = _LINEAR_FACTORS.get((source, target))
    if factor is None:
        return value, False
    return value * factor, True


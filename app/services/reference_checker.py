"""Service — Valeurs de référence par analyte/sexe/âge.

Pour chaque analyte d'un résultat, retourne un flag parmi :
  HH  →  très haute (> high_normal × 1.30)
  H   →  haute  (> high_normal)
  N   →  normale
  L   →  basse  (< low_normal)
  LL  →  très basse (< low_normal × 0.70)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.ruggylab_os import ReferenceRange
from app.services.critical_checker import _extract_numeric
from app.services.units import convert_value

# Facteur de seuil « très anormal »
_HH_FACTOR = 1.30
_LL_FACTOR = 0.70


def _age_in_years(birth_date: dt.date) -> float:
    today = dt.date.today()
    return (today - birth_date).days / 365.25


def compute_flags(
    data_points: dict,
    sex: str | None,
    birth_date: dt.date | None,
    db: Session,
) -> dict[str, str]:
    """Retourne un dict analyte → flag (HH/H/N/L/LL) pour chaque analyte trouvé.

    Si aucune plage de référence n'existe pour un analyte, l'analyte est ignoré.
    """
    ranges = db.query(ReferenceRange).filter(ReferenceRange.is_active.is_(True)).all()
    if not ranges:
        return {}

    age = _age_in_years(birth_date) if birth_date else None
    sex_upper = (sex or "*").upper()

    # Construire la meilleure correspondance par analyte
    # Priorité : plage spécifique au sexe > wildcard "*"
    range_map: dict[str, ReferenceRange] = {}
    for rr in ranges:
        analyte = rr.analyte.upper()
        # Filtrer par sexe
        if rr.sex not in ("*", sex_upper):
            continue
        # Filtrer par âge
        if age is not None:
            if rr.age_min_years is not None and age < rr.age_min_years:
                continue
            if rr.age_max_years is not None and age > rr.age_max_years:
                continue
        # Garder la plage la plus spécifique
        existing = range_map.get(analyte)
        if existing is None:
            range_map[analyte] = rr
        elif existing.sex == "*" and rr.sex != "*":
            # Plus spécifique sur le sexe → remplace
            range_map[analyte] = rr

    flags: dict[str, str] = {}
    for key, raw in data_points.items():
        value = _extract_numeric(raw)
        if value is None:
            continue
        ref = range_map.get(key.upper())
        if ref is None:
            continue
        source_unit = raw.get("unit") if isinstance(raw, dict) else None
        value, compatible = convert_value(value, source_unit, getattr(ref, "unit", None))
        if not compatible:
            continue

        lo = ref.low_normal
        hi = ref.high_normal

        if lo is not None and value < lo * _LL_FACTOR:
            flags[key.upper()] = "LL"
        elif lo is not None and value < lo:
            flags[key.upper()] = "L"
        elif hi is not None and value > hi * _HH_FACTOR:
            flags[key.upper()] = "HH"
        elif hi is not None and value > hi:
            flags[key.upper()] = "H"
        else:
            flags[key.upper()] = "N"

    return flags

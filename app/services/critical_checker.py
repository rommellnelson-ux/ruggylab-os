"""Service: detect critical values in a result's data_points.

A result is flagged critical when any analyte value falls outside the
configured critical range (below low_critical OR above high_critical).

data_points values may be:
  - plain numeric  : {"WBC": 5.2}
  - dict with key  : {"WBC": {"value": 5.2, "status": "N"}}   (DH36 / POCT format)
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CriticalRange


def _extract_numeric(v: object) -> float | None:
    """Return a float from a plain number or a dict containing 'value'."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        inner = v.get("value")
        if isinstance(inner, (int, float)):
            return float(inner)
    return None


def check_critical(data_points: dict, db: Session) -> bool:
    """Return True if any analyte in *data_points* exceeds a critical range.

    Comparison is case-insensitive on the analyte name.
    """
    ranges: list[CriticalRange] = (
        db.query(CriticalRange).filter(CriticalRange.is_active.is_(True)).all()
    )
    if not ranges:
        return False

    range_map = {r.analyte.upper(): r for r in ranges}

    for key, raw in data_points.items():
        value = _extract_numeric(raw)
        if value is None:
            continue
        cr = range_map.get(key.upper())
        if cr is None:
            continue
        if cr.low_critical is not None and value < cr.low_critical:
            return True
        if cr.high_critical is not None and value > cr.high_critical:
            return True

    return False

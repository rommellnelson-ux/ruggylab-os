"""Service — Delta-check patient.

Compare chaque nouvelle valeur d'analyte au résultat précédent du même patient.
Déclenche un flag si la variation absolue ou en pourcentage dépasse le seuil configuré.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import Result, Sample
from app.models.ruggylab_os import DeltaCheckRule
from app.services.critical_checker import _extract_numeric


def _get_previous_results(
    patient_id: int,
    max_lookback: int,
    db: Session,
) -> list[Result]:
    """Retourne les résultats récents pour un patient, du plus récent au plus ancien."""
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=max_lookback)
    return (
        db.query(Result)
        .join(Sample, Result.sample_id == Sample.id)
        .filter(
            Sample.patient_id == patient_id,
            Result.analysis_date >= cutoff,
        )
        .order_by(Result.analysis_date.desc())
        .all()
    )


def check_delta(
    data_points: dict,
    patient_id: int | None,
    db: Session,
) -> tuple[bool, dict]:
    """Vérifie le delta-check pour chaque analyte.

    Returns
    -------
    (delta_exceeded, delta_analytes)
        delta_exceeded  : True si au moins un analyte a dépassé son seuil
        delta_analytes  : dict analyte → variation observée (pour traçabilité)
    """
    if patient_id is None:
        return False, {}

    rules = (
        db.query(DeltaCheckRule)
        .filter(DeltaCheckRule.is_active.is_(True))
        .all()
    )
    if not rules:
        return False, {}

    rule_map: dict[str, DeltaCheckRule] = {r.analyte.upper(): r for r in rules}

    # Seuls les analytes présents dans les data_points ET dans les règles sont traités
    relevant = {k.upper() for k in data_points if k.upper() in rule_map}
    if not relevant:
        return False, {}

    max_lookback = max(rule_map[a].lookback_days for a in relevant)
    prev_results = _get_previous_results(patient_id, max_lookback, db)

    exceeded: dict[str, float] = {}

    for analyte in relevant:
        rule = rule_map[analyte]
        rule_cutoff = dt.datetime.utcnow() - dt.timedelta(days=rule.lookback_days)

        # Valeur actuelle
        current_value: float | None = None
        for k, v in data_points.items():
            if k.upper() == analyte:
                current_value = _extract_numeric(v)
                break
        if current_value is None:
            continue

        # Valeur précédente la plus récente dans la fenêtre
        prev_value: float | None = None
        for prev in prev_results:
            if prev.analysis_date is None or prev.analysis_date < rule_cutoff:
                continue
            if not prev.data_points:
                continue
            for k, v in prev.data_points.items():
                if k.upper() == analyte:
                    prev_value = _extract_numeric(v)
                    break
            if prev_value is not None:
                break

        if prev_value is None:
            # Pas de résultat antérieur → pas de flag (premier résultat)
            continue

        delta = current_value - prev_value
        triggered = False

        if rule.delta_abs is not None and abs(delta) >= rule.delta_abs:
            triggered = True
        if not triggered and rule.delta_pct is not None and prev_value != 0:
            pct = abs(delta / prev_value) * 100.0
            if pct >= rule.delta_pct:
                triggered = True

        if triggered:
            exceeded[analyte] = round(delta, 4)

    return bool(exceeded), exceeded

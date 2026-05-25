"""Service d'agrégation épidémiologique.

Calcule les statistiques par paramètre et par établissement (représenté
par l'équipement qui a produit le résultat) à partir de la table ``results``.

La colonne ``data_points`` est un JSON dont chaque valeur est un dict de la
forme ``{"value": <float>, "unit": <str>, "status": <str>}``.  Les statuts
``CRITICAL_LOW`` et ``CRITICAL_HIGH`` indiquent un résultat critique.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Equipment, Result, Sample
from app.schemas.epidemiology import (
    EpidemiologyDashboard,
    EpidemiologyRequest,
    FacilityStats,
    ParameterStats,
)

logger = logging.getLogger(__name__)

_CRITICAL_STATUSES: frozenset[str] = frozenset({"CRITICAL_LOW", "CRITICAL_HIGH"})


# ---------------------------------------------------------------------------
# Accumulateurs internes (non exposés)
# ---------------------------------------------------------------------------


@dataclass
class _ParamAcc:
    """Accumulateur pour un paramètre biologique."""

    total: int = 0
    critical: int = 0
    values: list[float] = field(default_factory=list)


@dataclass
class _FacilityAcc:
    """Accumulateur pour un équipement / établissement."""

    name: str | None = None
    total: int = 0
    critical: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_period(req: EpidemiologyRequest) -> tuple[datetime.date, datetime.date]:
    """Retourne (start_date, end_date) en appliquant les défauts si nécessaire."""
    today = datetime.date.today()
    end = req.end_date or today
    start = req.start_date or (end - datetime.timedelta(days=29))
    return start, end


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------


def compute_dashboard(db: Session, req: EpidemiologyRequest) -> EpidemiologyDashboard:
    """Calcule le tableau de bord épidémiologique.

    Args:
        db: Session SQLAlchemy.
        req: Paramètres de la requête (dates, filtres).

    Returns:
        Instance ``EpidemiologyDashboard`` avec toutes les agrégations.
    """
    start, end = _resolve_period(req)

    # Borne temporelle : inclure toute la journée de fin
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    # --- Requête de base ---
    query = (
        db.query(Result, Equipment)
        .outerjoin(Equipment, Result.equipment_id == Equipment.id)
        .join(Sample, Result.sample_id == Sample.id)
        .filter(Result.analysis_date >= start_dt, Result.analysis_date <= end_dt)
    )

    # Filtre optionnel par identifiant d'équipement (proxy pour l'établissement)
    if req.facility_ids:
        query = query.filter(Result.equipment_id.in_(req.facility_ids))

    rows = query.all()

    # --- Accumulateurs ---
    param_acc: dict[str, _ParamAcc] = defaultdict(_ParamAcc)
    facility_acc: dict[int | None, _FacilityAcc] = defaultdict(_FacilityAcc)
    daily_critical: dict[str, int] = defaultdict(int)

    total_results = 0
    total_critical = 0

    for result, equipment in rows:
        total_results += 1
        result_date = result.analysis_date.date().isoformat()

        equip_id: int | None = equipment.id if equipment else None
        fac = facility_acc[equip_id]
        if equipment is not None:
            fac.name = equipment.name
        fac.total += 1

        is_result_critical = False
        data_points: dict = result.data_points or {}

        for param_key, point in data_points.items():
            # Ignorer les clés non-analytiques (overall_flags, listes, etc.)
            if not isinstance(point, dict):
                continue
            if "value" not in point and "status" not in point:
                continue

            # Filtre sur les paramètres demandés
            if req.parameters and param_key not in req.parameters:
                continue

            status: str = str(point.get("status", ""))
            raw_value = point.get("value")
            is_critical_point = status in _CRITICAL_STATUSES

            acc = param_acc[param_key]
            acc.total += 1
            if is_critical_point:
                acc.critical += 1
                is_result_critical = True

            if raw_value is not None:
                with contextlib.suppress(TypeError, ValueError):
                    acc.values.append(float(raw_value))

        if is_result_critical:
            total_critical += 1
            fac.critical += 1
            daily_critical[result_date] += 1

    # --- Construction des ParameterStats ---
    parameter_stats: list[ParameterStats] = []
    for param, acc in param_acc.items():
        float_values = acc.values
        parameter_stats.append(
            ParameterStats(
                parameter=param,
                total_results=acc.total,
                critical_count=acc.critical,
                critical_rate=round(acc.critical / acc.total, 4) if acc.total > 0 else 0.0,
                mean_value=(
                    round(sum(float_values) / len(float_values), 4) if float_values else None
                ),
                min_value=min(float_values) if float_values else None,
                max_value=max(float_values) if float_values else None,
            )
        )
    # Tri décroissant par taux de critiques
    parameter_stats.sort(key=lambda s: s.critical_rate, reverse=True)

    # --- Construction des FacilityStats ---
    facility_stats: list[FacilityStats] = []
    for fid, fac in facility_acc.items():
        facility_stats.append(
            FacilityStats(
                facility_id=fid,
                facility_name=fac.name,
                total_results=fac.total,
                critical_count=fac.critical,
                critical_rate=round(fac.critical / fac.total, 4) if fac.total > 0 else 0.0,
            )
        )
    # Tri décroissant par nombre de critiques
    facility_stats.sort(key=lambda s: s.critical_count, reverse=True)

    # --- Tendance journalière ---
    daily_trend: list[dict] = [{"date": d, "count": c} for d, c in sorted(daily_critical.items())]

    overall_rate = round(total_critical / total_results, 4) if total_results > 0 else 0.0

    return EpidemiologyDashboard(
        period_start=start,
        period_end=end,
        total_results=total_results,
        total_critical=total_critical,
        overall_critical_rate=overall_rate,
        parameter_stats=parameter_stats,
        facility_stats=facility_stats,
        daily_critical_trend=daily_trend,
    )

"""Suivi du TAT (Turnaround Time) — délai de rendu des résultats biologiques.

Calcule, par résultat, les durées de phase (pré-analytique, analytique,
post-analytique, total) et un statut couleur par rapport au délai cible de
l'examen ; agrège des indicateurs de performance (par examen, technicien,
automate, journée) dans une logique d'amélioration continue ISO 15189.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import Result, TatTarget, User
from app.utils.datetime_utils import utcnow_naive


def _minutes_between(start: dt.datetime | None, end: dt.datetime | None) -> float | None:
    """Durée en minutes entre deux horodatages, ou None si incohérent/absent."""
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds() / 60.0
    if delta < 0:
        return None
    return round(delta, 1)


def tat_status(total_minutes: float | None, target: TatTarget | None) -> str:
    """Statut couleur : ``green`` / ``orange`` / ``red`` / ``unknown``.

    - vert   : dans les délais (≤ cible)
    - orange : retard modéré (≤ cible × warn_factor)
    - rouge  : retard important (> cible × warn_factor)
    """
    if total_minutes is None or target is None:
        return "unknown"
    if total_minutes <= target.target_minutes:
        return "green"
    if total_minutes <= target.target_minutes * target.warn_factor:
        return "orange"
    return "red"


def compute_result_tat(result: Result, target: TatTarget | None) -> dict:
    """Détail TAT d'un résultat : phases (minutes) + statut couleur."""
    total = _minutes_between(result.registered_at, result.bio_validated_at)
    pre = _minutes_between(result.prescribed_at, result.received_at)
    analytic = _minutes_between(result.analysis_started_at, result.analysis_finished_at)
    post = _minutes_between(result.analysis_finished_at, result.bio_validated_at)
    status = tat_status(total, target)
    return {
        "result_id": result.id,
        "exam_code": result.exam_code,
        "total_minutes": total,
        "pre_analytic_minutes": pre,
        "analytic_minutes": analytic,
        "post_analytic_minutes": post,
        "target_minutes": target.target_minutes if target else None,
        "status": status,
        "is_late": status in ("orange", "red"),
    }


def _targets_by_code(db: Session) -> dict[str, TatTarget]:
    return {
        t.exam_code: t
        for t in db.query(TatTarget).filter(TatTarget.is_active.is_(True)).all()
    }


def _agg(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"count": 0, "mean_min": 0.0, "min_min": 0.0, "max_min": 0.0}
    return {
        "count": n,
        "mean_min": round(sum(values) / n, 1),
        "min_min": round(min(values), 1),
        "max_min": round(max(values), 1),
    }


def compute_tat_dashboard(db: Session, days: int = 30) -> dict:
    """Tableau de bord TAT sur ``days`` jours (basé sur la validation biologique)."""
    cutoff = utcnow_naive() - dt.timedelta(days=days)
    targets = _targets_by_code(db)

    results = (
        db.query(Result)
        .filter(Result.bio_validated_at.isnot(None), Result.bio_validated_at >= cutoff)
        .all()
    )

    # Pré-chargement des noms de techniciens (validateurs)
    validator_ids = {r.validator_id for r in results if r.validator_id}
    user_names: dict[int, str] = {}
    if validator_ids:
        for u in db.query(User).filter(User.id.in_(validator_ids)).all():
            user_names[u.id] = u.full_name or u.username

    by_exam: dict[str, list[float]] = {}
    by_tech: dict[str, list[float]] = {}
    by_automate: dict[str, list[float]] = {}
    by_day: dict[str, list[float]] = {}
    late_count = 0
    on_time_count = 0
    measured = 0

    for r in results:
        total = _minutes_between(r.registered_at, r.bio_validated_at)
        if total is None:
            continue
        measured += 1
        target = targets.get(r.exam_code) if r.exam_code else None
        status = tat_status(total, target)
        if status == "green":
            on_time_count += 1
        elif status in ("orange", "red"):
            late_count += 1

        exam_key = r.exam_code or "(non codé)"
        by_exam.setdefault(exam_key, []).append(total)
        tech_key = user_names.get(r.validator_id, "(inconnu)") if r.validator_id else "(inconnu)"
        by_tech.setdefault(tech_key, []).append(total)
        auto_key = r.equipment.name if r.equipment else "Manuel"
        by_automate.setdefault(auto_key, []).append(total)
        day_key = r.bio_validated_at.date().isoformat()
        by_day.setdefault(day_key, []).append(total)

    # % rendus dans les délais (parmi ceux ayant un statut défini)
    qualified = on_time_count + late_count
    on_time_pct = round(on_time_count / qualified * 100, 1) if qualified else 0.0

    def _series(d: dict[str, list[float]], key_name: str) -> list[dict]:
        out = [{key_name: k, **_agg(vals)} for k, vals in d.items()]
        return sorted(out, key=lambda e: e["mean_min"], reverse=True)

    # Détail par examen avec taux de respect (cible connue)
    exam_rows: list[dict] = []
    for code, vals in by_exam.items():
        target = targets.get(code)
        on_time = sum(1 for v in vals if tat_status(v, target) == "green") if target else 0
        late = sum(1 for v in vals if tat_status(v, target) in ("orange", "red")) if target else 0
        qual = on_time + late
        exam_rows.append(
            {
                "exam_code": code,
                "label": target.label if target else code,
                "target_minutes": target.target_minutes if target else None,
                **_agg(vals),
                "late_count": late,
                "on_time_pct": round(on_time / qual * 100, 1) if qual else None,
            }
        )
    exam_rows.sort(key=lambda e: e["mean_min"], reverse=True)

    return {
        "period_days": days,
        "total_measured": measured,
        "late_count": late_count,
        "on_time_count": on_time_count,
        "on_time_pct": on_time_pct,
        "by_exam": exam_rows,
        "by_technician": _series(by_tech, "technician"),
        "by_automate": _series(by_automate, "automate"),
        "by_day": sorted(
            [{"day": k, **_agg(v)} for k, v in by_day.items()],
            key=lambda e: e["day"],
        ),
    }


def list_tat_alerts(db: Session, days: int = 7, limit: int = 100) -> list[dict]:
    """Résultats récents dépassant leur délai cible (orange/rouge)."""
    cutoff = utcnow_naive() - dt.timedelta(days=days)
    targets = _targets_by_code(db)
    results = (
        db.query(Result)
        .filter(Result.bio_validated_at.isnot(None), Result.bio_validated_at >= cutoff)
        .order_by(Result.bio_validated_at.desc())
        .all()
    )
    alerts: list[dict] = []
    for r in results:
        if not r.exam_code or r.exam_code not in targets:
            continue
        detail = compute_result_tat(r, targets[r.exam_code])
        if detail["is_late"]:
            detail["sample_id"] = r.sample_id
            detail["bio_validated_at"] = (
                r.bio_validated_at.isoformat() if r.bio_validated_at else None
            )
            alerts.append(detail)
        if len(alerts) >= limit:
            break
    return alerts


DEFAULT_TARGETS = [
    {"exam_code": "NFS", "label": "Numération Formule Sanguine", "target_minutes": 60},
    {"exam_code": "GLYC", "label": "Glycémie", "target_minutes": 30},
    {"exam_code": "CREAT", "label": "Créatinine", "target_minutes": 120},
    {"exam_code": "GE", "label": "Goutte épaisse", "target_minutes": 60},
    {"exam_code": "ECBU", "label": "ECBU", "target_minutes": 72 * 60, "warn_factor": 1.0},
]


def seed_default_targets(db: Session) -> int:
    """Crée les délais cibles par défaut absents. Retourne le nombre créé."""
    created = 0
    for spec in DEFAULT_TARGETS:
        if db.query(TatTarget).filter(TatTarget.exam_code == spec["exam_code"]).first():
            continue
        db.add(
            TatTarget(
                exam_code=spec["exam_code"],
                label=spec["label"],
                target_minutes=spec["target_minutes"],
                warn_factor=spec.get("warn_factor", 1.5),
            )
        )
        created += 1
    if created:
        db.commit()
    return created

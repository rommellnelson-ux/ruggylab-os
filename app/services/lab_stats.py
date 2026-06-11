"""Statistiques de performance du laboratoire.

Calcule sur une fenêtre glissante :
- Volume total de résultats et taux de valeurs critiques
- TAT (turnaround time) par équipement en heures
- Volumes hebdomadaires (8 dernières semaines)
- Taux de violations QC
- Nombre de maintenances échues dans les 7 prochains jours
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ruggylab_os import EquipmentMaintenance, QcResult, Result, Sample
from app.utils.datetime_utils import utcnow_naive


def compute_stats_summary(db: Session, days: int = 30) -> dict:
    """Retourne un dict de statistiques agrégées sur ``days`` jours."""
    cutoff = utcnow_naive() - dt.timedelta(days=days)

    # ── Résultats de la période ───────────────────────────────────────────────
    results = (
        db.query(Result)
        .join(Sample, Result.sample_id == Sample.id)
        .filter(Result.analysis_date >= cutoff)
        .all()
    )

    total = len(results)
    critical = sum(1 for r in results if r.is_critical)
    critical_rate = round(critical / total * 100, 1) if total else 0.0

    # ── TAT par équipement (heures) ───────────────────────────────────────────
    tat_by_eq: dict[str, list[float]] = {}
    for r in results:
        if r.sample and r.sample.collection_date and r.analysis_date:
            tat_h = (r.analysis_date - r.sample.collection_date).total_seconds() / 3600
            if tat_h < 0:
                continue  # cohérence des données
            eq_name = r.equipment.name if r.equipment else "Manuel"
            tat_by_eq.setdefault(eq_name, []).append(tat_h)

    tat_stats: list[dict] = []
    for eq_name, tats in sorted(tat_by_eq.items()):
        s = sorted(tats)
        n = len(s)
        tat_stats.append(
            {
                "equipment": eq_name,
                "count": n,
                "mean_h": round(sum(s) / n, 2),
                "min_h": round(s[0], 2),
                "max_h": round(s[-1], 2),
                "p95_h": round(s[min(int(n * 0.95), n - 1)], 2),
            }
        )

    # ── Volumes hebdomadaires (8 semaines glissantes) ─────────────────────────
    num_weeks = 8
    now = utcnow_naive()
    weekly: list[dict] = []
    for w in range(num_weeks - 1, -1, -1):
        w_start = now - dt.timedelta(weeks=w + 1)
        w_end = now - dt.timedelta(weeks=w)
        count = (
            db.query(func.count(Result.id))
            .filter(Result.analysis_date >= w_start, Result.analysis_date < w_end)
            .scalar()
            or 0
        )
        label = "Sem. act." if w == 0 else w_start.strftime("%d/%m")
        weekly.append({"week": f"S-{w}" if w > 0 else "S0", "label": label, "count": count})

    # ── Violations QC ─────────────────────────────────────────────────────────
    qc_cutoff = utcnow_naive() - dt.timedelta(days=days)
    qc_total = (
        db.query(func.count(QcResult.id)).filter(QcResult.created_at >= qc_cutoff).scalar() or 0
    )
    qc_violations = (
        db.query(func.count(QcResult.id))
        .filter(
            QcResult.created_at >= qc_cutoff,
            QcResult.violations.isnot(None),
            QcResult.violations != "[]",
            QcResult.violations != "null",
            QcResult.violations != "",
        )
        .scalar()
        or 0
    )
    qc_violation_rate = round(qc_violations / qc_total * 100, 1) if qc_total else 0.0

    # ── Maintenances à venir (≤ 7 jours) ─────────────────────────────────────
    due_cutoff = utcnow_naive() + dt.timedelta(days=7)
    maintenance_due = (
        db.query(func.count(EquipmentMaintenance.id))
        .filter(
            EquipmentMaintenance.is_completed.is_(False),
            EquipmentMaintenance.next_due_at.isnot(None),
            EquipmentMaintenance.next_due_at <= due_cutoff,
        )
        .scalar()
        or 0
    )

    return {
        "period_days": days,
        "total_results": total,
        "critical_results": critical,
        "critical_rate_pct": critical_rate,
        "tat_by_equipment": tat_stats,
        "weekly_volumes": weekly,
        "qc_total": qc_total,
        "qc_violations": qc_violations,
        "qc_violation_rate_pct": qc_violation_rate,
        "maintenance_due_count": maintenance_due,
    }

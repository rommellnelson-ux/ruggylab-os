"""Hub de notifications temps-réel.

Construit un instantané ("snapshot") agrégé des alertes actives du laboratoire :
  - valeurs critiques non-acquittées
  - résultats récents avec delta-check dépassé
  - réactifs proches de la péremption (ou expirés)
  - contrôles qualité en rejet (Westgard)

Ce snapshot alimente :
  - GET /notifications/feed   (polling REST, testable)
  - WebSocket /notifications/ws (push périodique)

Aucune dépendance externe — pure lecture base + réutilisation des services existants.
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy.orm import Session

from app.models import QcControl, QcResult, Result
from app.schemas.qc import QC_REJECT_RULES
from app.services.critical_notifier import get_pending_criticals
from app.services.expiry_notifier import get_expiring_reagents
from app.utils.datetime_utils import utcnow_naive


def _recent_delta_results(db: Session, hours: int = 48, limit: int = 20) -> list[dict]:
    """Résultats avec delta-check dépassé sur les ``hours`` dernières heures."""
    cutoff = utcnow_naive() - dt.timedelta(hours=hours)
    rows = (
        db.query(Result)
        .filter(Result.delta_exceeded.is_(True), Result.analysis_date >= cutoff)
        .order_by(Result.analysis_date.desc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for r in rows:
        analytes = list(r.delta_analytes.keys()) if isinstance(r.delta_analytes, dict) else []
        out.append(
            {
                "result_id": r.id,
                "sample_id": r.sample_id,
                "analysis_date": r.analysis_date.isoformat() if r.analysis_date else None,
                "analytes": analytes,
            }
        )
    return out


def _qc_rejects(db: Session) -> list[dict]:
    """Contrôles QC dont le dernier point déclenche une règle de rejet Westgard."""
    controls = db.query(QcControl).filter(QcControl.is_active.is_(True)).all()
    rejects: list[dict] = []
    for ctrl in controls:
        last = (
            db.query(QcResult)
            .filter(QcResult.control_id == ctrl.id)
            .order_by(QcResult.measured_at.desc(), QcResult.id.desc())
            .first()
        )
        if not last:
            continue
        violations = json.loads(last.violations or "[]")
        if any(v in QC_REJECT_RULES for v in violations):
            rejects.append(
                {
                    "control_id": ctrl.id,
                    "analyte": ctrl.analyte,
                    "level": ctrl.level,
                    "violations": violations,
                    "last_value": last.value,
                    "measured_at": last.measured_at.isoformat() if last.measured_at else None,
                }
            )
    return rejects


def build_alert_snapshot(db: Session, *, expiry_days: int = 7) -> dict:
    """Construit l'instantané complet des alertes actives.

    Returns un dict sérialisable JSON contenant les listes détaillées,
    les compteurs par catégorie et un total global, plus un horodatage.
    """
    criticals = get_pending_criticals(db)
    deltas = _recent_delta_results(db)
    expiring = get_expiring_reagents(db, days=expiry_days)
    qc_rejects = _qc_rejects(db)

    counts = {
        "criticals": len(criticals),
        "deltas": len(deltas),
        "expiring": len(expiring),
        "qc_rejects": len(qc_rejects),
    }
    total = sum(counts.values())

    return {
        "generated_at": utcnow_naive().isoformat(),
        "total": total,
        "counts": counts,
        "criticals": criticals,
        "deltas": deltas,
        "expiring": expiring,
        "qc_rejects": qc_rejects,
    }

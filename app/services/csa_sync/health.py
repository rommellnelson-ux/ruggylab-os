"""Observabilité de l'intégration CSA (I4) : état consolidé de la synchro.

``sync_health`` agrège, sans effet de bord, l'état des deux flux (entrant/sortant),
la file de résultats en attente de remontée, et le rapport des examens non mappés
(codes CSA à curer dans ``exam_map``). Sert au script de statut et à un éventuel
endpoint d'administration / export de métriques.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CsaSyncState, ExamOrder, ExamOrderItem

from .outbound import _find_result, pending_items


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def unmapped_report(db: Session) -> list[dict]:
    """Codes CSA arrivés sans correspondance (``exam_code`` ``CSA:*``), agrégés.

    Chaque entrée : ``{code, label, count}``. C'est la liste à curer dans
    ``exam_map.CSA_TO_RUGGYLAB`` — jamais deviné, toujours signalé.
    """
    rows = (
        db.query(
            ExamOrderItem.exam_code,
            ExamOrderItem.exam_label,
            func.count(ExamOrderItem.id).label("n"),
        )
        .filter(ExamOrderItem.exam_code.like("CSA:%"))
        .group_by(ExamOrderItem.exam_code, ExamOrderItem.exam_label)
        .all()
    )
    return sorted(
        ({"code": c, "label": lbl, "count": int(n)} for c, lbl, n in rows),
        key=lambda r: (-r["count"], r["code"]),
    )


def sync_health(db: Session) -> dict:
    """État consolidé de l'intégration CSA (lecture seule)."""
    state = db.get(CsaSyncState, 1)

    # File sortante : items éligibles non poussés (avec vs sans résultat prêt).
    pend = pending_items(db)
    ready = sum(1 for it in pend if _find_result(db, it.order, it) is not None)

    csa_orders = (
        db.query(func.count(ExamOrder.id))
        .filter(ExamOrder.csa_prescription_id.isnot(None))
        .scalar()
    ) or 0
    pushed_items = (
        db.query(func.count(ExamOrderItem.id))
        .join(ExamOrder, ExamOrderItem.order_id == ExamOrder.id)
        .filter(ExamOrder.csa_prescription_id.isnot(None), ExamOrderItem.csa_pushed_at.isnot(None))
        .scalar()
    ) or 0

    unmapped = unmapped_report(db)
    return {
        "inbound": {
            "last_run_at": _iso(getattr(state, "last_run_at", None)),
            "watermark": getattr(state, "last_pulled_at", None),
            "processed_count": getattr(state, "processed_count", 0) or 0,
            "last_error": getattr(state, "last_error", None),
        },
        "outbound": {
            "last_run_at": _iso(getattr(state, "last_outbound_run_at", None)),
            "pushed_count": getattr(state, "pushed_count", 0) or 0,
            "last_error": getattr(state, "last_outbound_error", None),
            "pending_total": len(pend),  # items en attente (échantillon prélevé)
            "pending_ready": ready,  # dont résultat validé prêt à remonter
        },
        "orders": {
            "csa_orders_total": int(csa_orders),
            "items_pushed_total": int(pushed_items),
        },
        "unmapped_exams": unmapped,
        "healthy": (
            (state is None or state.last_error is None)
            and (state is None or getattr(state, "last_outbound_error", None) is None)
        ),
    }

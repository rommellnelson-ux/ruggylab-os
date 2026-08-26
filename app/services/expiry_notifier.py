"""Alertes de péremption des réactifs.

Scanne les réactifs dont la date d'expiration est dans les N prochains jours
et envoie des notifications webhook via les NotifConfig actifs.
Aucune dépendance externe — utilise le transport HTTP sûr centralisé.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy.orm import Session

from app.models.ruggylab_os import NotifConfig, Reagent
from app.utils.safe_http import safe_post_json

logger = logging.getLogger(__name__)


def get_expiring_reagents(db: Session, days: int = 30) -> list[dict]:
    """Retourne la liste des réactifs expirant dans moins de ``days`` jours."""
    cutoff = dt.date.today() + dt.timedelta(days=days)
    reagents = (
        db.query(Reagent)
        .filter(
            Reagent.expiry_date.isnot(None),
            Reagent.expiry_date <= cutoff,
        )
        .order_by(Reagent.expiry_date.asc())
        .all()
    )
    today = dt.date.today()
    result = []
    for r in reagents:
        if r.expiry_date is None:  # garanti par le filtre, mais explicite pour le typage
            continue
        days_remaining = (r.expiry_date - today).days
        result.append(
            {
                "id": r.id,
                "name": r.name,
                "lot_number": r.lot_number,
                "expiry_date": r.expiry_date.isoformat(),
                "days_remaining": days_remaining,
                "is_expired": days_remaining < 0,
                "current_stock": r.current_stock,
                "unit": r.unit,
            }
        )
    return result


def check_and_notify_expiry(db: Session, days: int = 30) -> dict:
    """Envoie des webhooks pour les réactifs expirant bientôt.

    Réutilise la table ``notif_configs`` (webhook_url actif).
    Retourne ``{"notified": int, "expiring": int}``.
    """
    expiring = get_expiring_reagents(db, days=days)
    if not expiring:
        return {"notified": 0, "expiring": 0}

    configs = (
        db.query(NotifConfig)
        .filter(NotifConfig.is_active.is_(True), NotifConfig.webhook_url.isnot(None))
        .all()
    )
    notified = 0
    payload_bytes = json.dumps(
        {
            "event": "reagent_expiry_alert",
            "days_window": days,
            "expiring_count": len(expiring),
            "expiring": expiring[:20],  # cap to avoid oversized payloads
        }
    ).encode()
    for cfg in configs:
        url = cfg.webhook_url
        # Garde anti-SSRF : refuse loopback, IP privées, métadonnées cloud, etc.
        if not url:
            continue
        try:
            status_code = safe_post_json(url, payload_bytes, timeout=5)
            if 200 <= status_code < 300:
                notified += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("expiry_notifier.webhook.error err=%s", exc)
            continue
    return {"notified": notified, "expiring": len(expiring)}

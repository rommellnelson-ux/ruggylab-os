"""Alertes de péremption des réactifs.

Scanne les réactifs dont la date d'expiration est dans les N prochains jours
et envoie des notifications webhook via les NotifConfig actifs.
Aucune dépendance externe — utilise uniquement urllib.request.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import urllib.request

from sqlalchemy.orm import Session

from app.models.ruggylab_os import NotifConfig, Reagent
from app.utils.url_safety import is_safe_external_url


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
        # Garde anti-SSRF : refuse loopback, IP privées, métadonnées cloud, etc.
        if not is_safe_external_url(cfg.webhook_url):
            continue
        req = urllib.request.Request(  # noqa: S310
            cfg.webhook_url,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with contextlib.suppress(Exception):
            with urllib.request.urlopen(req, timeout=5):  # noqa: S310  # nosec B310
                pass
            notified += 1
    return {"notified": notified, "expiring": len(expiring)}

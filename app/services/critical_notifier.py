"""Service — Notifications pour valeurs critiques non-acquittées.

Surveille les résultats critiques non-acquittés depuis plus de `delay_minutes`
et envoie des webhooks HTTP POST (stdlib uniquement, aucune dépendance externe).
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Result
from app.models.ruggylab_os import NotifConfig
from app.utils.datetime_utils import utcnow_naive
from app.utils.url_safety import is_safe_external_url


def _send_webhook(url: str, payload: dict) -> bool:
    """Envoie un POST JSON à `url`. Retourne True si HTTP 2xx."""
    # Garde anti-SSRF : refuse loopback, IP privées, métadonnées cloud, etc.
    if not is_safe_external_url(url):
        return False
    if urlparse(url).scheme not in {"http", "https"}:
        return False

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - scheme restricted above
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310  # nosec B310
            return bool(resp.status < 400)
    except Exception:  # noqa: BLE001
        return False


def get_pending_criticals(db: Session, delay_minutes: int = 30) -> list[dict]:
    """Retourne tous les résultats critiques non-acquittés avec le délai écoulé."""
    unacked = (
        db.query(Result)
        .filter(
            Result.is_critical.is_(True),
            Result.critical_ack_at.is_(None),
        )
        .order_by(Result.analysis_date.asc())
        .all()
    )

    now = utcnow_naive()
    result = []
    for r in unacked:
        elapsed = int((now - r.analysis_date).total_seconds() / 60) if r.analysis_date else 0
        result.append(
            {
                "result_id": r.id,
                "sample_id": r.sample_id,
                "analysis_date": r.analysis_date.isoformat() if r.analysis_date else None,
                "elapsed_minutes": elapsed,
                "overdue": elapsed >= delay_minutes,
            }
        )
    return result


def check_and_notify(db: Session) -> dict:
    """Envoie les webhooks configurés pour les critiques en retard d'acquittement.

    Returns
    -------
    {"notified": int, "pending": int}
    """
    configs = db.query(NotifConfig).filter(NotifConfig.is_active.is_(True)).all()
    if not configs:
        pending = (
            db.query(Result)
            .filter(Result.is_critical.is_(True), Result.critical_ack_at.is_(None))
            .count()
        )
        return {"notified": 0, "pending": pending}

    # Délai minimum parmi les configs actives
    min_delay = min(c.delay_minutes for c in configs)
    global_cutoff = utcnow_naive() - dt.timedelta(minutes=min_delay)

    unacked_all = (
        db.query(Result)
        .filter(
            Result.is_critical.is_(True),
            Result.critical_ack_at.is_(None),
            Result.analysis_date <= global_cutoff,
        )
        .all()
    )

    total_pending = (
        db.query(Result)
        .filter(Result.is_critical.is_(True), Result.critical_ack_at.is_(None))
        .count()
    )

    notified = 0
    for config in configs:
        config_cutoff = utcnow_naive() - dt.timedelta(minutes=config.delay_minutes)
        pending_for_config = [r for r in unacked_all if r.analysis_date <= config_cutoff]
        if not pending_for_config:
            continue
        if config.webhook_url:
            payload = {
                "alert_type": "critical_unacked",
                "count": len(pending_for_config),
                "result_ids": [r.id for r in pending_for_config],
                "generated_at": utcnow_naive().isoformat(),
            }
            if _send_webhook(config.webhook_url, payload):
                notified += len(pending_for_config)

    return {"notified": notified, "pending": total_pending}

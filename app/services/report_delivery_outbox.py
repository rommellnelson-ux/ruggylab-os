"""Traitement resilient de la file d'envoi des comptes-rendus.

Le snapshot du compte-rendu est cree dans la transaction metier. Cette file
sert ensuite a diffuser le document sans risquer de perdre l'evenement si un
canal externe est indisponible.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ReportDeliveryOutbox
from app.utils.datetime_utils import utcnow_naive


SUPPORTED_LOCAL_CHANNELS = {"internal"}
TERMINAL_STATUSES = {"processed", "dead_letter"}
RETRYABLE_STATUSES = {"pending", "failed"}


@dataclass(frozen=True)
class DeliveryAttemptResult:
    """Resultat d'un passage de worker outbox."""

    processed: int = 0
    retried: int = 0
    dead_lettered: int = 0
    skipped: int = 0


def _backoff_delay(attempt_count: int) -> dt.timedelta:
    """Retourne un backoff exponentiel borne, adapte aux micro-coupures reseau."""

    seconds = min(15 * (2 ** max(attempt_count - 1, 0)), 30 * 60)
    return dt.timedelta(seconds=seconds)


def _mark_processed(event: ReportDeliveryOutbox) -> None:
    event.status = "processed"
    event.processed_at = utcnow_naive()
    event.last_error = None


def _mark_failed(
    event: ReportDeliveryOutbox,
    *,
    error: str,
    max_attempts: int,
) -> bool:
    event.attempt_count += 1
    event.last_error = error[:2000]
    if event.attempt_count >= max_attempts:
        event.status = "dead_letter"
        event.next_attempt_at = None
        return True
    event.status = "failed"
    event.next_attempt_at = utcnow_naive() + _backoff_delay(event.attempt_count)
    return False


def process_report_delivery_outbox(
    db: Session,
    *,
    limit: int = 50,
    max_attempts: int = 8,
    dispatchers: dict[str, Callable[[ReportDeliveryOutbox], None]] | None = None,
) -> DeliveryAttemptResult:
    """Traite les evenements d'envoi dus.

    Par defaut seul le canal ``internal`` est consomme localement: il signifie
    que le compte-rendu est disponible dans RuggyLab et que l'evenement peut
    etre cloture. Les canaux externes doivent fournir un dispatcher explicite
    pour eviter les faux positifs d'envoi en production.
    """

    now = utcnow_naive()
    events = (
        db.query(ReportDeliveryOutbox)
        .filter(ReportDeliveryOutbox.status.in_(RETRYABLE_STATUSES))
        .filter(
            (ReportDeliveryOutbox.next_attempt_at.is_(None))
            | (ReportDeliveryOutbox.next_attempt_at <= now)
        )
        .order_by(ReportDeliveryOutbox.created_at.asc(), ReportDeliveryOutbox.id.asc())
        .limit(limit)
        .all()
    )
    processed = retried = dead_lettered = skipped = 0
    dispatchers = dispatchers or {}

    for event in events:
        if event.status in TERMINAL_STATUSES:
            skipped += 1
            continue

        try:
            dispatcher = dispatchers.get(event.channel)
            if dispatcher is not None:
                dispatcher(event)
            elif event.channel in SUPPORTED_LOCAL_CHANNELS:
                _mark_processed(event)
                processed += 1
                continue
            else:
                raise RuntimeError(f"Canal de diffusion non configure: {event.channel}")
        except Exception as exc:  # noqa: BLE001 - le worker doit isoler chaque evenement.
            is_terminal = _mark_failed(event, error=str(exc), max_attempts=max_attempts)
            if is_terminal:
                dead_lettered += 1
            else:
                retried += 1
        else:
            _mark_processed(event)
            processed += 1

    db.commit()
    return DeliveryAttemptResult(
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
        skipped=skipped,
    )

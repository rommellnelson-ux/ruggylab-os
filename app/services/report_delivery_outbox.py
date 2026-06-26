"""Traitement resilient de la file d'envoi des comptes-rendus.

Le snapshot du compte-rendu est cree dans la transaction metier. Cette file
sert ensuite a diffuser le document sans risquer de perdre l'evenement si un
canal externe est indisponible.
"""

from __future__ import annotations

import datetime as dt
import json
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ReportDeliveryOutbox
from app.services.fhir_builder import build_diagnostic_report
from app.services.report_signing import build_snapshot_pdf
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


def _safe_filename(value: object) -> str:
    raw = str(value or "unknown").strip()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    return safe.strip("-") or "unknown"


def _snapshot_pdf_filename(event: ReportDeliveryOutbox) -> str:
    snapshot = event.report_snapshot
    return (
        f"result-{_safe_filename(snapshot.result_id)}"
        f"-v{_safe_filename(snapshot.version_number)}"
        f"-snapshot-{_safe_filename(snapshot.id)}.pdf"
    )


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def dispatch_snapshot_pdf_to_filesystem(
    event: ReportDeliveryOutbox,
    *,
    output_dir: str | Path | None = None,
) -> None:
    """Depose le PDF fige dans un dossier local controle par l'exploitation."""

    target_dir = Path(output_dir or settings.REPORT_DELIVERY_OUTPUT_DIR)
    pdf_path = target_dir / _snapshot_pdf_filename(event)
    _write_bytes_atomic(pdf_path, build_snapshot_pdf(event.report_snapshot))
    payload = dict(event.payload or {})
    payload["pdf_path"] = str(pdf_path)
    event.payload = payload


def dispatch_snapshot_fhir_to_filesystem(
    event: ReportDeliveryOutbox,
    *,
    output_dir: str | Path | None = None,
) -> None:
    """Exporte un DiagnosticReport FHIR JSON pour le resultat du snapshot."""

    result = event.report_snapshot.result
    if result is None:
        raise RuntimeError("Resultat absent du snapshot: export FHIR impossible.")
    bundle = build_diagnostic_report(result).model_dump(mode="json")
    target_dir = Path(output_dir or settings.REPORT_DELIVERY_FHIR_DIR)
    json_path = (
        target_dir / f"result-{_safe_filename(result.id)}"
        f"-v{_safe_filename(event.report_snapshot.version_number)}.json"
    )
    _write_text_atomic(json_path, json.dumps(bundle, ensure_ascii=False, indent=2))
    payload = dict(event.payload or {})
    payload["fhir_path"] = str(json_path)
    event.payload = payload


def dispatch_snapshot_email(event: ReportDeliveryOutbox) -> None:
    """Envoie le PDF du snapshot via SMTP configure."""

    recipient = (event.payload or {}).get("email_to") or settings.REPORT_DELIVERY_EMAIL_TO
    if not recipient:
        raise RuntimeError("Destinataire email non configure.")

    snapshot = event.report_snapshot
    msg = EmailMessage()
    msg["Subject"] = f"RuggyLab OS - compte-rendu #{snapshot.result_id} v{snapshot.version_number}"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = str(recipient)
    msg.set_content(
        "Veuillez trouver ci-joint le compte-rendu RuggyLab OS. "
        "Ce document medical doit etre traite selon les procedures de confidentialite."
    )
    msg.add_attachment(
        build_snapshot_pdf(snapshot),
        maintype="application",
        subtype="pdf",
        filename=_snapshot_pdf_filename(event),
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


def default_report_delivery_dispatchers() -> dict[str, Callable[[ReportDeliveryOutbox], None]]:
    """Dispatchers actifs par defaut pour les canaux de compte-rendu."""

    return {
        "patient_portal": dispatch_snapshot_pdf_to_filesystem,
        "filesystem": dispatch_snapshot_pdf_to_filesystem,
        "fhir": dispatch_snapshot_fhir_to_filesystem,
        "email": dispatch_snapshot_email,
        "prescriber": dispatch_snapshot_email,
    }


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
    dispatchers = default_report_delivery_dispatchers() if dispatchers is None else dispatchers

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

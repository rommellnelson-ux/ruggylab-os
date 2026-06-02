"""
StockNotifier — Notifications d'alerte de rupture de stock CMU Côte d'Ivoire
=============================================================================

Envoie des alertes de stock par webhook (HTTP POST) et/ou email (SMTP).

Dépendances stdlib uniquement :
  - urllib.request pour les appels HTTP
  - smtplib pour l'envoi d'emails
"""

from __future__ import annotations

import logging
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.text import MIMEText

from app.core.config import settings
from app.schemas.notification import (
    DrugAlertSummary,
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
    NotificationSeverity,
    StockAlertNotification,
)
from app.schemas.stock_predictor import (
    AlertLevel,
    PredictionRequest,
    StockPredictionLine,
)
from app.services.stock_predictor import get_stock_predictor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class StockNotifier:
    """Envoie des alertes de stock par webhook et/ou email (SMTP)."""

    _predictor_factory: object = field(default_factory=get_stock_predictor, repr=False)

    def notify(self, request: NotificationRequest) -> NotificationResult:
        """Prédit les stocks, filtre par sévérité, envoie les alertes."""
        from app.services.stock_predictor import StockPredictor  # éviter import circulaire

        predictor: StockPredictor = (
            self._predictor_factory
            if isinstance(self._predictor_factory, StockPredictor)
            else get_stock_predictor()
        )

        pred_request = PredictionRequest(
            drugs=request.drugs,
            reference_date=request.reference_date,
            horizon_days=request.horizon_days,
            include_fhir=False,
        )
        prediction = predictor.predict(pred_request)

        # Filtrer les lignes selon la sévérité demandée
        filtered_lines = self._filter_by_severity(
            prediction.drug_predictions, request.severity_filter
        )

        if not filtered_lines:
            logger.info("stock_notifier.notify: aucun médicament à notifier")
            return NotificationResult(
                prediction_summary=prediction,
                notifications_sent=0,
                channels_used=[],
                drugs_notified=[],
                errors=[],
            )

        # Construire le payload de notification
        drug_summaries = [
            DrugAlertSummary(
                dci_code=line.dci_code,
                alert_level=line.alert_level,
                months_remaining=line.months_of_stock_remaining,
                estimated_rupture_date=line.estimated_rupture_date,
                suggested_order_qty=line.suggested_order_qty,
                reorder_cost_xof=line.reorder_cost_xof,
            )
            for line in filtered_lines
        ]

        payload = StockAlertNotification(
            timestamp=datetime.now(tz=UTC),
            facility_id=request.facility_id,
            critical_count=prediction.critical_count,
            alert_count=prediction.alert_count,
            drugs_at_risk=drug_summaries,
            fhir_bundle_url=None,
        )

        channels_used: list[str] = []
        errors: list[str] = []
        notifications_sent = 0

        # Envoi webhook
        if request.channel in (NotificationChannel.WEBHOOK, NotificationChannel.BOTH):
            if request.webhook_url:
                ok = self._send_webhook(request.webhook_url, payload)
                if ok:
                    channels_used.append("WEBHOOK")
                    notifications_sent += 1
                else:
                    errors.append(f"Échec envoi webhook vers {request.webhook_url}")
            else:
                errors.append("webhook_url requis pour channel WEBHOOK/BOTH")

        # Envoi email
        if request.channel in (NotificationChannel.EMAIL, NotificationChannel.BOTH):
            if request.email_to:
                ok = self._send_email(request.email_to, payload)
                if ok:
                    channels_used.append("EMAIL")
                    notifications_sent += 1
                else:
                    errors.append(f"Échec envoi email vers {request.email_to}")
            else:
                errors.append("email_to requis pour channel EMAIL/BOTH")

        drugs_notified = [s.dci_code for s in drug_summaries]

        return NotificationResult(
            prediction_summary=prediction,
            notifications_sent=notifications_sent,
            channels_used=channels_used,
            drugs_notified=drugs_notified,
            errors=errors,
        )

    def _send_webhook(self, url: str, payload: StockAlertNotification) -> bool:
        """POST JSON au webhook. Timeout 10s. Retourne True si 2xx."""
        timeout = settings.NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS
        body = payload.model_dump_json().encode("utf-8")
        req = urllib.request.Request(  # noqa: S310
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RuggyLab-StockNotifier/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
                status_code: int = resp.status
                if 200 <= status_code < 300:
                    logger.info("stock_notifier.webhook.ok url=%s status=%d", url, status_code)
                    return True
                logger.warning("stock_notifier.webhook.non2xx url=%s status=%d", url, status_code)
                return False
        except urllib.error.HTTPError as exc:
            logger.error(
                "stock_notifier.webhook.http_error url=%s status=%d err=%s",
                url,
                exc.code,
                exc,
            )
            return False
        except Exception as exc:
            logger.error("stock_notifier.webhook.error url=%s err=%s", url, exc)
            return False

    def _send_email(self, to: list[str], payload: StockAlertNotification) -> bool:
        """Envoie un email de résumé via smtplib (SMTP stub configurable)."""
        subject = (
            f"[RuggyLab] Alerte rupture de stock — "
            f"{payload.critical_count} critique(s), {payload.alert_count} alerte(s)"
        )
        body_lines = [
            "=== ALERTE RUPTURE DE STOCK — RuggyLab CMU ===",
            f"Date : {payload.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
        ]
        if payload.facility_id:
            body_lines.append(f"Etablissement : {payload.facility_id}")

        body_lines += [
            "",
            f"Médicaments critiques : {payload.critical_count}",
            f"Médicaments en alerte  : {payload.alert_count}",
            "",
            "--- Détail des médicaments à risque ---",
        ]
        for drug in payload.drugs_at_risk:
            rupture_str = (
                drug.estimated_rupture_date.isoformat()
                if drug.estimated_rupture_date
                else "inconnue"
            )
            cost_str = (
                f"{drug.reorder_cost_xof} XOF" if drug.reorder_cost_xof is not None else "N/A"
            )
            body_lines.append(
                f"  {drug.dci_code} | {drug.alert_level} | "
                f"{drug.months_remaining:.1f} mois | rupture {rupture_str} | "
                f"cmd: {drug.suggested_order_qty} u. ({cost_str})"
            )

        body_lines += [
            "",
            "-- RuggyLab OS · alertes@ruggylab.local",
        ]
        body_text = "\n".join(body_lines)

        msg = MIMEText(body_text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = ", ".join(to)

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.SMTP_FROM, to, msg.as_string())
            logger.info("stock_notifier.email.ok to=%s", to)
            return True
        except Exception as exc:
            logger.error("stock_notifier.email.error to=%s err=%s", to, exc)
            return False

    def _filter_by_severity(
        self,
        lines: list[StockPredictionLine],
        severity: NotificationSeverity,
    ) -> list[StockPredictionLine]:
        """Filtre les lignes de prédiction selon le niveau de sévérité souhaité."""
        if severity == NotificationSeverity.RUPTURE_IMMINENTE:
            return [ln for ln in lines if ln.alert_level == AlertLevel.RUPTURE_IMMINENTE]

        if severity == NotificationSeverity.ALERTE_ET_PLUS:
            return [
                ln
                for ln in lines
                if ln.alert_level
                in (
                    AlertLevel.ALERTE,
                    AlertLevel.ALERTE_CRITIQUE,
                    AlertLevel.RUPTURE_IMMINENTE,
                )
            ]

        # TOUTES — tout sauf OK
        return [ln for ln in lines if ln.alert_level != AlertLevel.OK]


# ---------------------------------------------------------------------------
# Singleton applicatif
# ---------------------------------------------------------------------------

_notifier: StockNotifier | None = None


def get_stock_notifier() -> StockNotifier:
    """Factory / singleton FastAPI-injectable."""
    global _notifier
    if _notifier is None:
        _notifier = StockNotifier()
    return _notifier

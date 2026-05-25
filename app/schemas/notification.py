"""
Schémas Pydantic — Notifications d'alerte de rupture de stock CMU Côte d'Ivoire.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from app.schemas.stock_predictor import (
    AlertLevel,
    DrugStockInput,
    PredictionHorizon,
    PredictionResult,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NotificationChannel(StrEnum):
    WEBHOOK = "WEBHOOK"
    EMAIL = "EMAIL"
    BOTH = "BOTH"


class NotificationSeverity(StrEnum):
    RUPTURE_IMMINENTE = "RUPTURE_IMMINENTE"  # uniquement critiques
    ALERTE_ET_PLUS = "ALERTE_ET_PLUS"  # ALERTE + ALERTE_CRITIQUE + RUPTURE
    TOUTES = "TOUTES"  # toutes sauf OK


# ---------------------------------------------------------------------------
# Résumé par médicament
# ---------------------------------------------------------------------------


class DrugAlertSummary(BaseModel):
    """Résumé d'alerte pour un médicament donné."""

    dci_code: str
    alert_level: AlertLevel
    months_remaining: float
    estimated_rupture_date: date | None
    suggested_order_qty: int
    reorder_cost_xof: Decimal | None


# ---------------------------------------------------------------------------
# Payload de notification
# ---------------------------------------------------------------------------


class StockAlertNotification(BaseModel):
    """Payload envoyé au webhook ou par email."""

    timestamp: datetime
    facility_id: str | None  # identifiant de l'officine (optionnel)
    critical_count: int
    alert_count: int
    drugs_at_risk: list[DrugAlertSummary]  # sous-ensemble filtré par sévérité
    fhir_bundle_url: str | None  # lien vers le bundle FHIR si généré


# ---------------------------------------------------------------------------
# Requête / Résultat
# ---------------------------------------------------------------------------


class NotificationRequest(BaseModel):
    """Requête pour déclencher une vérification + notification."""

    drugs: list[DrugStockInput]
    horizon_days: PredictionHorizon = PredictionHorizon.NINETY_DAYS
    reference_date: date | None = None
    channel: NotificationChannel
    severity_filter: NotificationSeverity
    facility_id: str | None = None
    webhook_url: str | None = None  # requis si channel=WEBHOOK ou BOTH
    email_to: list[str] | None = None  # requis si channel=EMAIL ou BOTH


class NotificationResult(BaseModel):
    """Résultat de l'opération de notification."""

    prediction_summary: PredictionResult
    notifications_sent: int
    channels_used: list[str]
    drugs_notified: list[str]
    errors: list[str]

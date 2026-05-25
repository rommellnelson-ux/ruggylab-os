"""
API — Notifications d'alerte de rupture de stock CMU Côte d'Ivoire
===================================================================

Endpoint :
  POST /stock/notify  → Déclenche une prédiction de stocks et envoie les alertes
                        par webhook et/ou email selon le seuil de sévérité configuré.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.notification import NotificationRequest, NotificationResult
from app.services.notifier import StockNotifier, get_stock_notifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock", tags=["Stock Predictor CMU"])


@router.post(
    "/notify",
    response_model=NotificationResult,
    status_code=status.HTTP_200_OK,
    summary="Notification d'alerte de rupture de stock",
    description=(
        "Calcule les prédictions de stock avec saisonnalité épidémiologique CI, "
        "filtre les médicaments selon le seuil de sévérité demandé, "
        "puis envoie les alertes par webhook et/ou email."
    ),
)
def trigger_stock_notification(
    payload: NotificationRequest,
    notifier: StockNotifier = Depends(get_stock_notifier),
    _current_user: User = Depends(get_current_active_user),
) -> NotificationResult:
    """Prédit les stocks et envoie les alertes selon la sévérité configurée."""
    try:
        result = notifier.notify(payload)
    except Exception as exc:
        logger.exception("stock_notifier.endpoint.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du module de notification de stocks.",
        ) from exc

    logger.info(
        "stock_notifier.endpoint.ok",
        extra={
            "notifications_sent": result.notifications_sent,
            "channels_used": result.channels_used,
            "drugs_notified_count": len(result.drugs_notified),
        },
    )
    return result

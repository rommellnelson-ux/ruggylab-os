"""
API — StockPredictor CMU Côte d'Ivoire
======================================

Endpoints :
  POST /stock/predict      → Prédiction de stocks avec saisonnalité épidémiologique CI
  POST /stock/cmm-history  → Calcul CMM depuis un historique de consommations
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.stock_predictor import PredictionRequest, PredictionResult
from app.services.stock_predictor import StockPredictor, get_stock_predictor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock", tags=["Stock Predictor CMU"])


class CMMHistoryRequest:
    """Corps de la requête CMM par historique (simple inline model)."""

    pass


from pydantic import BaseModel, Field  # noqa: E402  (import après la classe factice)


class CMMHistoryPayload(BaseModel):
    """Consommations mensuelles historiques pour le calcul du CMM."""

    dci_code: str
    monthly_consumptions: list[float] = Field(
        min_length=1,
        description="Consommations mensuelles (valeurs absolues), de la plus ancienne à la plus récente",
        examples=[[120.0, 135.0, 0.0, 148.0, 130.0]],
    )


class CMMHistoryResult(BaseModel):
    dci_code: str
    cmm_computed: int
    months_of_data: int
    excluded_zero_months: int


@router.post(
    "/predict",
    response_model=PredictionResult,
    status_code=status.HTTP_200_OK,
    summary="Prédiction de stocks avec saisonnalité épidémiologique CI",
    description=(
        "Calcule l'évolution prévisionnelle du stock de chaque médicament en appliquant "
        "le profil saisonnier épidémiologique de la Côte d'Ivoire (données PNLP/OMS). "
        "Génère des alertes OMS/MSF et, optionnellement, un bundle FHIR MedicationRequest "
        "pour les réapprovisionnements urgents."
    ),
)
def predict_stock(
    payload: PredictionRequest,
    predictor: StockPredictor = Depends(get_stock_predictor),
    _current_user: User = Depends(get_current_active_user),
) -> PredictionResult:
    """Prédit l'état des stocks à l'horizon demandé."""
    try:
        result = predictor.predict(payload)
    except Exception as exc:
        logger.exception("stock_predictor.predict.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du moteur de prédiction de stocks.",
        ) from exc

    logger.info(
        "stock_predictor.predict.ok",
        extra={
            "total_drugs": result.total_drugs,
            "critical_count": result.critical_count,
            "horizon_days": result.horizon_days,
        },
    )
    return result


@router.post(
    "/cmm-history",
    response_model=CMMHistoryResult,
    status_code=status.HTTP_200_OK,
    summary="Calcul CMM depuis un historique de consommations",
    description=(
        "Calcule la Consommation Mensuelle Moyenne (CMM) selon la méthode OMS/MSF : "
        "moyenne des mois non nuls (les ruptures de stock sont exclues du calcul). "
        "Le résultat est arrondi à l'unité supérieure (règle OMS)."
    ),
)
def compute_cmm_from_history(
    payload: CMMHistoryPayload,
    predictor: StockPredictor = Depends(get_stock_predictor),
    _current_user: User = Depends(get_current_active_user),
) -> CMMHistoryResult:
    """Calcule le CMM depuis un historique mensuel de consommations."""
    cmm = predictor.compute_cmm_from_history(payload.monthly_consumptions)
    zero_months = sum(1 for m in payload.monthly_consumptions if m == 0)
    return CMMHistoryResult(
        dci_code=payload.dci_code.upper(),
        cmm_computed=cmm,
        months_of_data=len(payload.monthly_consumptions),
        excluded_zero_months=zero_months,
    )

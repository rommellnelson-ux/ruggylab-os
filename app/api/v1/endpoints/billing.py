"""
API — Moteur de Facturation CMU Côte d'Ivoire
=============================================

Endpoints :
  POST /billing/calculate   → Calcul de facture (assuré ou non-assuré)
  POST /billing/cmm-report  → Rapport Consommation Mensuelle Moyenne (OMS/MSF)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.billing import (
    BillingRequest,
    BillingResult,
    CMMEntryResponse,
    CMMReportRequest,
)
from app.services.billing_engine import BillingEngine, get_billing_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing CMU"])


@router.post(
    "/calculate",
    response_model=BillingResult,
    status_code=status.HTTP_200_OK,
    summary="Calcul de facture hybride CMU (assuré / non-assuré)",
    description=(
        "Calcule la répartition CNAM 70 % / Ticket Modérateur 30 % pour un patient assuré, "
        "ou applique les remises de programme (générique, aide sociale) pour un patient non-assuré. "
        "Les codes **CIM-10** (pathologie) et **DCI** (médicament) sont obligatoires."
    ),
)
def calculate_bill(
    payload: BillingRequest,
    engine: BillingEngine = Depends(get_billing_engine),
    _current_user: User = Depends(get_current_active_user),
) -> BillingResult:
    """Calcule une facture CMU-CI complète."""
    try:
        result = engine.process(payload)
    except ValueError as exc:
        logger.warning("billing.calculate.validation_error", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("billing.calculate.unexpected_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du moteur de facturation.",
        ) from exc

    logger.info(
        "billing.calculate.ok",
        extra={
            "patient_type": result.patient_type,
            "net_total_xof": str(result.net_total_xof),
            "cnam_coverage_xof": str(result.cnam_coverage_xof),
            "patient_due_xof": str(result.patient_due_xof),
        },
    )
    return result


@router.post(
    "/cmm-report",
    response_model=list[CMMEntryResponse],
    status_code=status.HTTP_200_OK,
    summary="Rapport CMM — Consommation Mensuelle Moyenne (OMS/MSF)",
    description=(
        "Génère un rapport de gestion des stocks basé sur le modèle CMM de l'OMS/MSF. "
        "Les médicaments en rupture imminente (< 2 mois de stock) apparaissent en tête de liste. "
        "La quantité suggérée à commander vise 6 mois de couverture."
    ),
)
def cmm_report(
    payload: CMMReportRequest,
    engine: BillingEngine = Depends(get_billing_engine),
    _current_user: User = Depends(get_current_active_user),
) -> list[CMMEntryResponse]:
    """Calcule le rapport CMM et retourne les médicaments triés par criticité."""
    try:
        entries = engine.compute_cmm_report(payload)
        return [CMMEntryResponse.from_entry(e) for e in entries]
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("billing.cmm_report.validation_error", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Données CMM invalides : {exc}",
        ) from exc

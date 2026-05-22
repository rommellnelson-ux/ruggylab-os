"""
API — PrescriptionScanner CMU Côte d'Ivoire
============================================

Endpoints :
  POST /prescription/scan          → Validation complète d'une ordonnance
  POST /prescription/interactions  → Vérification d'interactions seule (sans profil patient)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.billing import DCICode
from app.schemas.prescription_scanner import (
    DrugInteractionFlag,
    InteractionSeverity,
    PrescriptionLine,
    PrescriptionRequest,
    ScanResult,
)
from app.services.prescription_scanner import PrescriptionScanner, get_prescription_scanner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prescription", tags=["Prescription Scanner CMU"])


# ---------------------------------------------------------------------------
# Endpoint 1 : scan complet
# ---------------------------------------------------------------------------


@router.post(
    "/scan",
    response_model=ScanResult,
    status_code=status.HTTP_200_OK,
    summary="Validation complète d'une ordonnance CMU",
    description=(
        "Analyse une ordonnance selon les règles CMU Côte d'Ivoire : "
        "codes CIM-10 et DCI obligatoires, détection d'interactions médicamenteuses "
        "(classification OMS/ANSM), contre-indications liées au profil patient "
        "(G6PD, grossesse, âge, insuffisance rénale/hépatique), vérification posologique "
        "et authenticité QR-code. "
        "Retourne un statut VALID / WARNING / BLOCKED avec score de confiance."
    ),
)
def scan_prescription(
    payload: PrescriptionRequest,
    scanner: PrescriptionScanner = Depends(get_prescription_scanner),
    _current_user: User = Depends(get_current_active_user),
) -> ScanResult:
    """Valide une ordonnance complète et retourne le rapport de conformité CMU."""
    try:
        result = scanner.scan(payload)
    except Exception as exc:
        logger.exception("prescription_scanner.scan.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne du scanner d'ordonnance.",
        ) from exc

    logger.info(
        "prescription_scanner.scan.ok",
        extra={
            "status": result.status,
            "confidence": result.confidence_score,
            "interactions": result.interaction_count,
            "contraindications": result.contraindication_count,
            "blocked_drugs": result.blocked_drugs,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Endpoint 2 : vérification d'interactions seule (outil pharmacien)
# ---------------------------------------------------------------------------


class InteractionCheckPayload(BaseModel):
    """Requête de vérification d'interactions pour une liste de DCI."""

    dci_codes: list[str] = Field(
        min_length=2,
        description="Liste de codes DCI à vérifier (minimum 2)",
        examples=[["ARTEMETHER-LUMEFANTRINE", "QUININE", "AMIODARONE"]],
    )


class InteractionCheckResult(BaseModel):
    """Résultat de la vérification d'interactions pour une liste de DCI."""

    dci_codes: list[str]
    interactions_found: list[DrugInteractionFlag]
    interaction_count: int
    has_contraindicated: bool
    has_major: bool


@router.post(
    "/interactions",
    response_model=InteractionCheckResult,
    status_code=status.HTTP_200_OK,
    summary="Vérification rapide d'interactions médicamenteuses",
    description=(
        "Détecte les interactions médicamenteuses entre une liste de DCI "
        "sans nécessiter de profil patient complet. "
        "Utile pour une vérification rapide au comptoir. "
        "Retourne toutes les paires détectées avec leur niveau de gravité (OMS/ANSM)."
    ),
)
def check_interactions(
    payload: InteractionCheckPayload,
    scanner: PrescriptionScanner = Depends(get_prescription_scanner),
    _current_user: User = Depends(get_current_active_user),
) -> InteractionCheckResult:
    """Vérifie les interactions entre les DCI fournis."""
    try:
        normalised = [c.strip().upper() for c in payload.dci_codes]
        lines = [PrescriptionLine(dci=DCICode(code=dci)) for dci in normalised]
        interactions = scanner._check_interactions(lines)  # noqa: SLF001
    except Exception as exc:
        logger.exception("prescription_scanner.interactions.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification des interactions.",
        ) from exc

    return InteractionCheckResult(
        dci_codes=normalised,
        interactions_found=interactions,
        interaction_count=len(interactions),
        has_contraindicated=any(
            i.severity == InteractionSeverity.CONTRAINDICATED for i in interactions
        ),
        has_major=any(i.severity == InteractionSeverity.MAJOR for i in interactions),
    )

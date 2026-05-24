"""
API — FHIR R4 Pharmacy Endpoints
=================================

Complète le cycle pharmacie CMU avec les ressources FHIR manquantes :

  POST /fhir/medication-dispense  → Bundle MedicationDispense
      Génère un ou plusieurs MedicationDispense à partir d'une dispensation
      validée (ordonnance VALID + facturation CMU traitée).

  POST /fhir/supply-delivery      → Bundle SupplyDelivery
      Génère un ou plusieurs SupplyDelivery à partir de la réception d'un
      réassort commandé via StockPredictor (MedicationRequest → livraison).

Cycle complet documenté :
  PrescriptionScanner → VALID
    → BillingEngine.calculate         (facturation CMU)
      → /fhir/medication-dispense     (traçabilité dispensation)

  StockPredictor.predict (include_fhir=True)
    → MedicationRequest bundle        (commande réassort)
      → /fhir/supply-delivery         (confirmation livraison reçue)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.fhir import MedicationDispenseRequest, SupplyDeliveryRequest
from app.services.fhir_builder import (
    build_medication_dispense_bundle,
    build_supply_delivery_bundle,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fhir", tags=["FHIR R4 Pharmacy"])

_FHIR_CONTENT_TYPE = "application/fhir+json"


@router.post(
    "/medication-dispense",
    status_code=status.HTTP_200_OK,
    summary="Génère un Bundle FHIR R4 MedicationDispense",
    description=(
        "Produit un Bundle FHIR R4 ``collection`` contenant un **MedicationDispense** "
        "par médicament dispensé. À appeler après validation de l'ordonnance "
        "(PrescriptionScanner → VALID) et calcul de la facture CMU "
        "(BillingEngine → BillingResult).\n\n"
        "Chaque ressource contient :\n"
        "- Médicament (code DCI OMS / ATC)\n"
        "- Quantité dispensée\n"
        "- Patient (référence IPP)\n"
        "- Pharmacien dispensateur (optionnel)\n"
        "- Posologie (dose, fréquence, durée)\n"
        "- Référence dossier CMU CNAM (traçabilité)"
    ),
    response_description="Bundle FHIR R4 MedicationDispense (application/fhir+json)",
)
def create_medication_dispense(
    payload: MedicationDispenseRequest,
    _current_user: User = Depends(get_current_active_user),
) -> JSONResponse:
    """Génère un bundle FHIR MedicationDispense depuis une dispensation CMU."""
    bundle: dict[str, Any] = build_medication_dispense_bundle(payload)

    logger.info(
        "fhir.medication_dispense.created",
        extra={
            # patient_ref et cnam_billing_ref sont PHI — on ne les logue pas en clair
            "has_patient_ref": bool(payload.patient_ref),
            "drug_count": len(payload.drug_lines),
            "has_cnam_billing_ref": bool(payload.cnam_billing_ref),
            "has_prescription_ref": bool(payload.authorizing_prescription_ref),
        },
    )

    return JSONResponse(
        content=bundle,
        media_type=_FHIR_CONTENT_TYPE,
    )


@router.post(
    "/supply-delivery",
    status_code=status.HTTP_200_OK,
    summary="Génère un Bundle FHIR R4 SupplyDelivery",
    description=(
        "Produit un Bundle FHIR R4 ``collection`` contenant un **SupplyDelivery** "
        "par article livré. À appeler lors de la réception physique d'un réassort "
        "commandé via ``POST /api/v1/stock/predict`` (MedicationRequest généré).\n\n"
        "Chaque ressource contient :\n"
        "- Médicament livré (code DCI OMS / ATC)\n"
        "- Quantité reçue\n"
        "- Fournisseur (grossiste / NPSP Côte d'Ivoire)\n"
        "- Officine destinataire\n"
        "- Date de livraison\n"
        "- Valorisation XOF, lot, date de péremption (optionnels)\n"
        "- Référence MedicationRequest de la commande initiale (optionnel)"
    ),
    response_description="Bundle FHIR R4 SupplyDelivery (application/fhir+json)",
)
def create_supply_delivery(
    payload: SupplyDeliveryRequest,
    _current_user: User = Depends(get_current_active_user),
) -> JSONResponse:
    """Génère un bundle FHIR SupplyDelivery depuis une livraison de réassort."""
    bundle: dict[str, Any] = build_supply_delivery_bundle(payload)

    logger.info(
        "fhir.supply_delivery.created",
        extra={
            "supplier": payload.supplier_name,
            "destination": payload.destination_pharmacy_id,
            "item_count": len(payload.items),
            "order_ref": payload.order_reference,
        },
    )

    return JSONResponse(
        content=bundle,
        media_type=_FHIR_CONTENT_TYPE,
    )

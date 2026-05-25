"""
API — Rapport PDF d'ordonnance CMU Côte d'Ivoire
=================================================

Endpoint :
  POST /prescription/report   → PDF A4 structuré de l'ordonnance scannée
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_active_user
from app.models.ruggylab_os import User
from app.schemas.prescription_scanner import PrescriptionRequest
from app.services.pdf_prescription import build_prescription_report
from app.services.prescription_scanner import PrescriptionScanner, get_prescription_scanner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prescription", tags=["Prescription Scanner CMU"])


@router.post(
    "/report",
    status_code=status.HTTP_200_OK,
    summary="Rapport PDF d'ordonnance CMU",
    description=(
        "Valide l'ordonnance via le scanner CMU (CIM-10 + DCI, interactions, "
        "contre-indications, QR-code) puis génère un rapport PDF A4 structuré. "
        "Retourne le fichier PDF en pièce jointe."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Rapport PDF de l'ordonnance CMU.",
        }
    },
)
def generate_prescription_report(
    payload: PrescriptionRequest,
    scanner: PrescriptionScanner = Depends(get_prescription_scanner),
    _current_user: User = Depends(get_current_active_user),
) -> Response:
    """Scanne l'ordonnance et retourne le rapport PDF A4."""
    try:
        result = scanner.scan(payload)
    except Exception as exc:
        logger.exception("pdf_prescription.scan.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la validation de l'ordonnance.",
        ) from exc

    try:
        pdf_bytes = build_prescription_report(payload, result)
    except Exception as exc:
        logger.exception("pdf_prescription.build.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la génération du rapport PDF.",
        ) from exc

    date_str = (
        str(payload.prescription_date)
        if payload.prescription_date
        else str(date.today())
    )
    filename = f"ordonnance-{date_str}.pdf"

    logger.info(
        "pdf_prescription.report.ok",
        extra={
            "status": result.status,
            "confidence": result.confidence_score,
            "pdf_filename": filename,
        },
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

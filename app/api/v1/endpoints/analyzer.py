"""Ingestion sécurisée des résultats automates via middleware ASTM."""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.analyzer import AnalyzerResultIngest, AnalyzerResultIngestResponse
from app.services.analyzer_ingestion import AnalyzerIngestionError, ingest_analyzer_result

router = APIRouter(prefix="/analyzer")


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else ""
    if direct in settings.TRUSTED_PROXY_IPS:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return direct


async def _verify_analyzer_security(
    request: Request,
    x_analyzer_key: str | None = Header(default=None, alias="X-Analyzer-Key"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_analyzer_timestamp: str | None = Header(default=None, alias="X-Analyzer-Timestamp"),
    x_analyzer_signature: str | None = Header(default=None, alias="X-Analyzer-Signature"),
) -> None:
    if not settings.ANALYZER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion automate non configuree.",
        )

    if settings.ANALYZER_ALLOWED_IPS and _client_ip(request) not in settings.ANALYZER_ALLOWED_IPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Adresse middleware non autorisee.",
        )

    provided_key = x_analyzer_key or x_api_key or ""
    if not hmac.compare_digest(provided_key, settings.ANALYZER_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cle middleware automate invalide.",
        )

    if settings.ANALYZER_HMAC_SECRET:
        if not x_analyzer_timestamp or not x_analyzer_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signature middleware automate manquante.",
            )
        try:
            timestamp = int(x_analyzer_timestamp)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Horodatage signature invalide.",
            ) from exc
        skew = abs(int(time.time()) - timestamp)
        if skew > settings.ANALYZER_SIGNATURE_MAX_SKEW_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signature middleware automate expiree.",
            )
        body = await request.body()
        signed = f"{x_analyzer_timestamp}.".encode() + body
        expected = hmac.new(
            settings.ANALYZER_HMAC_SECRET.encode("utf-8"),
            signed,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_analyzer_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signature middleware automate invalide.",
            )


@router.post(
    "/results",
    response_model=AnalyzerResultIngestResponse,
    dependencies=[Depends(_verify_analyzer_security)],
)
async def receive_analyzer_results(
    payload: AnalyzerResultIngest,
    db: Session = Depends(get_db),
) -> dict:
    """Reçoit un lot résultat déjà parsé par le middleware automate.

    Cette route est volontairement séparée de /results: elle utilise une
    authentification machine-to-machine, applique l'idempotence, et journalise
    explicitement la source automate.
    """
    try:
        return ingest_analyzer_result(db, payload)
    except AnalyzerIngestionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        db.rollback()
        raise

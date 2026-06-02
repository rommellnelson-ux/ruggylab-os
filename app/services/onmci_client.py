"""
ONMCIClient — Vérification QR-code d'ordonnance
================================================

Stratégie à 2 niveaux :
  1. Vérification locale HMAC-SHA256 (rapide, offline-capable)
     Token attendu = HMAC-SHA256(prescriber_id + "|" + date_iso, ONMCI_SECRET_KEY)
     Le token est encodé en hex (64 chars).

  2. Vérification distante (si ONMCI_API_URL configurée)
     GET {ONMCI_API_URL}/verify?token={token}&prescriber={prescriber_id}
     Réponse JSON : {"valid": true/false, "prescriber_name": "...", "license_active": true}
     Timeout : ONMCI_TIMEOUT_SECONDS (défaut 5s)
     En cas d'erreur réseau : fallback sur vérification locale.

Architecture :
  Python 3.11+ · urllib.request (stdlib, pas httpx) · hmac · hashlib
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

logger = logging.getLogger(__name__)

# Fenêtre de tolérance d'horodatage : aujourd'hui + 2 jours précédents
_DATE_WINDOW_DAYS: Final[int] = 3


@dataclass(frozen=True)
class ONMCIVerificationResult:
    """Résultat d'une vérification QR-code ONMCI."""

    valid: bool
    method: str  # "HMAC_LOCAL" | "ONMCI_API" | "FORMAT_ONLY"
    prescriber_name: str | None
    license_active: bool | None
    error: str | None  # message d'erreur si fallback


@dataclass
class ONMCIClient:
    """
    Client de vérification QR-code pour l'Ordre National des Médecins de Côte d'Ivoire.

    Essaie l'API distante en premier (si configurée), puis bascule sur
    la vérification HMAC locale, et enfin sur le simple contrôle de format.
    """

    secret_key: str  # ONMCI_SECRET_KEY depuis config
    api_url: str | None  # ONMCI_API_URL, None = offline seulement
    timeout_seconds: int  # défaut 5

    def verify(self, token: str | None, prescriber_id: str | None) -> ONMCIVerificationResult:
        """Point d'entrée principal — essaie l'API distante puis fallback HMAC local."""
        if not token or not prescriber_id:
            return ONMCIVerificationResult(
                valid=False,
                method="FORMAT_ONLY",
                prescriber_name=None,
                license_active=None,
                error="token ou prescriber_id manquant",
            )

        cleaned_token = token.strip().lower()
        cleaned_prescriber = prescriber_id.strip()

        # Niveau 2 : API distante
        if self.api_url:
            remote_result = self._verify_remote(cleaned_token, cleaned_prescriber)
            if remote_result is not None:
                return remote_result
            # Fallback HMAC si erreur réseau
            logger.warning(
                "onmci_client.remote_failed",
                extra={"prescriber_id": cleaned_prescriber},
            )

        # Niveau 1 : HMAC local
        hmac_valid = self._verify_hmac(cleaned_token, cleaned_prescriber)
        if hmac_valid:
            return ONMCIVerificationResult(
                valid=True,
                method="HMAC_LOCAL",
                prescriber_name=None,
                license_active=None,
                error=None,
            )

        # Niveau 0 : vérification de format uniquement
        format_valid = self._verify_format(cleaned_token)
        return ONMCIVerificationResult(
            valid=format_valid,
            method="FORMAT_ONLY",
            prescriber_name=None,
            license_active=None,
            error=None if format_valid else "token invalide (format et HMAC)",
        )

    def _verify_hmac(self, token: str, prescriber_id: str) -> bool:
        """
        Vérifie HMAC-SHA256 pour la date du jour ET les 2 jours précédents.

        Tolérance de ±2 jours pour absorber les décalages d'horodatage.
        Token valide si HMAC(prescriber_id + "|" + any_of_last_3_days) == token.
        """
        today = date.today()
        for delta in range(_DATE_WINDOW_DAYS):
            ref_date = today - timedelta(days=delta)
            expected = _make_token(prescriber_id, self.secret_key, ref_date)
            if hmac.compare_digest(expected, token):
                return True
        return False

    def _verify_remote(self, token: str, prescriber_id: str) -> ONMCIVerificationResult | None:
        """
        Appel HTTP GET à l'API ONMCI.

        Retourne None si erreur réseau (pour déclencher le fallback HMAC local).
        Retourne un ONMCIVerificationResult si l'API répond (valide ou non).
        """
        assert self.api_url is not None  # garanti par l'appelant
        params = urllib.parse.urlencode({"token": token, "prescriber": prescriber_id})
        url = f"{self.api_url.rstrip('/')}/verify?{params}"

        try:
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
                raw = resp.read()
                data: dict[str, object] = json.loads(raw)

            valid = bool(data.get("valid", False))
            raw_name = data.get("prescriber_name")
            prescriber_name = str(raw_name) if raw_name is not None else None
            license_active_raw = data.get("license_active")
            license_active = bool(license_active_raw) if license_active_raw is not None else None

            return ONMCIVerificationResult(
                valid=valid,
                method="ONMCI_API",
                prescriber_name=prescriber_name,
                license_active=license_active,
                error=None,
            )

        except urllib.error.URLError as exc:
            logger.warning(
                "onmci_client.url_error",
                extra={"url": url, "error": str(exc)},
            )
            return None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "onmci_client.parse_error",
                extra={"url": url, "error": str(exc)},
            )
            return None

    def _verify_format(self, token: str) -> bool:
        """Fallback minimal : token hex ≥ 32 chars (ancien comportement)."""
        try:
            int(token, 16)
            return len(token) >= 32
        except ValueError:
            return False


def _make_token(prescriber_id: str, secret_key: str, ref_date: date | None = None) -> str:
    """
    Génère un token HMAC-SHA256 pour un prescripteur et une date donnée.

    Utilisé en production pour signer les QR-codes et dans les tests pour
    générer des tokens valides.
    """
    d = ref_date or date.today()
    msg = f"{prescriber_id}|{d.isoformat()}".encode()
    return hmac.new(secret_key.encode(), msg, hashlib.sha256).hexdigest()


def get_onmci_client() -> ONMCIClient:
    """Singleton injectable FastAPI."""
    from app.core.config import settings  # import tardif pour éviter les cycles

    return ONMCIClient(
        secret_key=settings.ONMCI_SECRET_KEY,
        api_url=settings.ONMCI_API_URL,
        timeout_seconds=settings.ONMCI_TIMEOUT_SECONDS,
    )

"""Client HTTP du contrat d'interopérabilité CSA Plateau (Supabase/PostgREST).

Léger, synchrone (``httpx.Client``) — pas de dépendance ``supabase-py``. Se
connecte via GoTrue avec les identifiants du compte technique RUGGYLAB, puis
appelle les deux RPC exposées par CSA. Les jetons sont rafraîchis sur 401.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class CsaEventSink(Protocol):
    """Contrat minimal attendu par le flux sortant : pousser un evenement CSA."""

    def push_event(self, kind: str, source_item_id: str, payload: dict) -> Any: ...


class CsaInboundSource(CsaEventSink, Protocol):
    """Contrat attendu par le flux entrant : tirer les prescriptions + accuser."""

    def pull_prescriptions(self, changed_since: str, max_rows: int = 100) -> list[dict]: ...


class CsaClient:
    def __init__(
        self,
        base_url: str,
        anon_key: str,
        email: str,
        password: str,
        *,
        timeout: float = 20.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._anon = anon_key
        self._email = email
        self._password = password
        self._http = httpx.Client(timeout=timeout)
        self._token: str | None = None

    def _login(self) -> None:
        resp = self._http.post(
            f"{self._base}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": self._anon, "Content-Type": "application/json"},
            json={"email": self._email, "password": self._password},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {
            "apikey": self._anon,
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _rpc(self, fn: str, body: dict[str, Any]) -> Any:
        url = f"{self._base}/rest/v1/rpc/{fn}"
        resp = self._http.post(url, headers=self._headers(), json=body)
        if resp.status_code == 401:  # jeton expiré -> re-login une fois
            self._token = None
            resp = self._http.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        return resp.json()

    def pull_prescriptions(self, changed_since: str, max_rows: int = 100) -> list[dict]:
        rows = self._rpc(
            "csa_ruggylab_pull_prescriptions",
            {"changed_since": changed_since, "max_rows": max_rows},
        )
        return rows or []

    def push_event(self, kind: str, source_item_id: str, payload: dict) -> Any:
        return self._rpc(
            "csa_ruggylab_push_event",
            {
                "event_kind": kind,
                "source_item_id": source_item_id,
                "event_payload": payload,
            },
        )

    def close(self) -> None:
        self._http.close()


def build_client_from_settings() -> CsaClient:
    if not settings.CSA_SUPABASE_URL:
        raise RuntimeError("CSA_SUPABASE_URL non configuré")
    return CsaClient(
        settings.CSA_SUPABASE_URL,
        settings.CSA_SUPABASE_ANON_KEY,
        settings.CSA_RUGGYLAB_EMAIL,
        settings.CSA_RUGGYLAB_PASSWORD,
    )

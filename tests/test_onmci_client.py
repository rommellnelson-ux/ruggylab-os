"""
Tests du client ONMCI — Vérification QR-code d'ordonnance
==========================================================

Couverture :
  - _verify_format : token hex ≥ 32 chars → True ; trop court → False ; non-hex → False
  - _verify_hmac : token valide aujourd'hui → True ; invalide → False ; hier → True (tolérance)
  - _verify_remote avec mock urllib : JSON {"valid": true} → ONMCIVerificationResult(valid=True)
  - _verify_remote erreur réseau → None (déclenchement du fallback)
  - verify() avec api_url=None → utilise HMAC local
  - verify() avec api_url configurée et réseau OK → utilise API distante
  - verify() avec api_url configurée et réseau KO → fallback HMAC
  - verify() token None → valid=False
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.onmci_client import (
    ONMCIClient,
    ONMCIVerificationResult,
    _make_token,
)

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

_SECRET = "test-secret-key-for-unit-tests-ok"  # pragma: allowlist secret
_PRESCRIBER = "ONMCI-99001"


def _client(api_url: str | None = None, secret: str = _SECRET) -> ONMCIClient:
    return ONMCIClient(
        secret_key=secret,
        api_url=api_url,
        timeout_seconds=5,
    )


def _valid_token(prescriber_id: str = _PRESCRIBER, delta_days: int = 0) -> str:
    """Génère un token HMAC valide pour le prescripteur, avec décalage optionnel."""
    ref = date.today() - timedelta(days=delta_days)
    return _make_token(prescriber_id, _SECRET, ref)


# ---------------------------------------------------------------------------
# 1. _verify_format
# ---------------------------------------------------------------------------


class TestVerifyFormat:
    def test_hex_32_chars_valid(self) -> None:
        client = _client()
        assert client._verify_format("a" * 32) is True  # noqa: SLF001

    def test_hex_64_chars_valid(self) -> None:
        client = _client()
        assert client._verify_format("f" * 64) is True  # noqa: SLF001

    def test_hex_31_chars_invalid(self) -> None:
        client = _client()
        assert client._verify_format("a" * 31) is False  # noqa: SLF001

    def test_non_hex_invalid(self) -> None:
        client = _client()
        assert client._verify_format("z" * 32) is False  # noqa: SLF001

    def test_empty_string_invalid(self) -> None:
        client = _client()
        assert client._verify_format("") is False  # noqa: SLF001

    def test_mixed_valid_hex(self) -> None:
        client = _client()
        # SHA-256 hex réel
        token = hashlib.sha256(b"test").hexdigest()  # 64 chars
        assert client._verify_format(token) is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# 2. _verify_hmac
# ---------------------------------------------------------------------------


class TestVerifyHMAC:
    def test_valid_token_today(self) -> None:
        client = _client()
        token = _valid_token()
        assert client._verify_hmac(token, _PRESCRIBER) is True  # noqa: SLF001

    def test_valid_token_yesterday(self) -> None:
        """Token généré hier → doit être accepté (tolérance 2j)."""
        client = _client()
        token = _valid_token(delta_days=1)
        assert client._verify_hmac(token, _PRESCRIBER) is True  # noqa: SLF001

    def test_valid_token_2_days_ago(self) -> None:
        """Token généré il y a 2 jours → doit être accepté (tolérance 2j)."""
        client = _client()
        token = _valid_token(delta_days=2)
        assert client._verify_hmac(token, _PRESCRIBER) is True  # noqa: SLF001

    def test_invalid_token_3_days_ago(self) -> None:
        """Token généré il y a 3 jours → hors fenêtre → rejeté."""
        client = _client()
        token = _valid_token(delta_days=3)
        assert client._verify_hmac(token, _PRESCRIBER) is False  # noqa: SLF001

    def test_wrong_secret_key(self) -> None:
        """Token généré avec une autre clé → rejeté."""
        other_client = _client(secret="other-secret-entirely-different")
        token = _valid_token()
        assert other_client._verify_hmac(token, _PRESCRIBER) is False  # noqa: SLF001

    def test_wrong_prescriber_id(self) -> None:
        """Token pour prescripteur A → rejeté pour prescripteur B."""
        client = _client()
        token = _valid_token(prescriber_id="ONMCI-00001")
        assert client._verify_hmac(token, "ONMCI-00002") is False  # noqa: SLF001

    def test_tampered_token(self) -> None:
        """Token valide modifié d'un caractère → rejeté."""
        client = _client()
        token = list(_valid_token())
        token[0] = "0" if token[0] != "0" else "1"
        assert client._verify_hmac("".join(token), _PRESCRIBER) is False  # noqa: SLF001

    def test_make_token_helper(self) -> None:
        """_make_token produit 64 caractères hex."""
        token = _make_token(_PRESCRIBER, _SECRET)
        assert len(token) == 64
        int(token, 16)  # doit être un hex valide


# ---------------------------------------------------------------------------
# 3. _verify_remote avec mock urllib
# ---------------------------------------------------------------------------


class TestVerifyRemote:
    def _mock_response(self, payload: dict[str, object], status: int = 200) -> MagicMock:
        """Crée un mock de réponse urllib qui se comporte comme un context manager."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.status = status
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_remote_valid_response(self) -> None:
        """API retourne valid=true → result.valid=True, method=ONMCI_API."""
        client = _client(api_url="https://api.onmci.ci")
        payload = {
            "valid": True,
            "prescriber_name": "Dr. Kouamé",
            "license_active": True,
        }
        mock_resp = self._mock_response(payload)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._verify_remote("abc" * 22, _PRESCRIBER)  # noqa: SLF001

        assert result is not None
        assert result.valid is True
        assert result.method == "ONMCI_API"
        assert result.prescriber_name == "Dr. Kouamé"
        assert result.license_active is True
        assert result.error is None

    def test_remote_invalid_response(self) -> None:
        """API retourne valid=false → result.valid=False, method=ONMCI_API."""
        client = _client(api_url="https://api.onmci.ci")
        payload = {"valid": False, "prescriber_name": None, "license_active": False}
        mock_resp = self._mock_response(payload)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._verify_remote("bad-token", _PRESCRIBER)  # noqa: SLF001

        assert result is not None
        assert result.valid is False
        assert result.method == "ONMCI_API"

    def test_remote_network_error_returns_none(self) -> None:
        """Erreur réseau URLError → retourne None (déclenche fallback)."""
        client = _client(api_url="https://api.onmci.ci")

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connexion refusée"),
        ):
            result = client._verify_remote(_valid_token(), _PRESCRIBER)  # noqa: SLF001

        assert result is None

    def test_remote_json_parse_error_returns_none(self) -> None:
        """Réponse JSON malformée → retourne None."""
        client = _client(api_url="https://api.onmci.ci")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not-json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._verify_remote(_valid_token(), _PRESCRIBER)  # noqa: SLF001

        assert result is None

    def test_remote_partial_response_no_prescriber_name(self) -> None:
        """Réponse sans prescriber_name → prescriber_name=None."""
        client = _client(api_url="https://api.onmci.ci")
        payload = {"valid": True}
        mock_resp = self._mock_response(payload)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._verify_remote(_valid_token(), _PRESCRIBER)  # noqa: SLF001

        assert result is not None
        assert result.valid is True
        assert result.prescriber_name is None
        assert result.license_active is None


# ---------------------------------------------------------------------------
# 4. verify() — méthode publique principale
# ---------------------------------------------------------------------------


class TestVerify:
    def test_verify_token_none(self) -> None:
        """Token None → valid=False, method=FORMAT_ONLY."""
        client = _client()
        result = client.verify(None, _PRESCRIBER)
        assert result.valid is False
        assert result.method == "FORMAT_ONLY"
        assert result.error is not None

    def test_verify_prescriber_none(self) -> None:
        """prescriber_id None → valid=False."""
        client = _client()
        result = client.verify(_valid_token(), None)
        assert result.valid is False

    def test_verify_both_none(self) -> None:
        """Token et prescripteur None → valid=False."""
        client = _client()
        result = client.verify(None, None)
        assert result.valid is False

    def test_verify_hmac_local_no_api(self) -> None:
        """api_url=None → utilise HMAC local. Token valide → valid=True."""
        client = _client(api_url=None)
        token = _valid_token()
        result = client.verify(token, _PRESCRIBER)
        assert result.valid is True
        assert result.method == "HMAC_LOCAL"

    def test_verify_invalid_hmac_no_api_format_fallback(self) -> None:
        """api_url=None, HMAC invalide, mais format hex ≥ 32 → FORMAT_ONLY, valid=True."""
        client = _client(api_url=None)
        # Token hex valide mais ne correspond pas au HMAC attendu
        token = "a" * 64
        result = client.verify(token, _PRESCRIBER)
        assert result.valid is True
        assert result.method == "FORMAT_ONLY"

    def test_verify_invalid_hmac_no_api_short_token(self) -> None:
        """api_url=None, HMAC invalide, format invalide (trop court) → valid=False."""
        client = _client(api_url=None)
        result = client.verify("deadbeef", _PRESCRIBER)
        assert result.valid is False

    def test_verify_with_api_url_success(self) -> None:
        """api_url configurée, API répond valid=true → method=ONMCI_API, valid=True."""
        client = _client(api_url="https://api.onmci.ci")
        payload = {"valid": True, "prescriber_name": "Dr. Test", "license_active": True}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.verify(_valid_token(), _PRESCRIBER)

        assert result.valid is True
        assert result.method == "ONMCI_API"

    def test_verify_with_api_url_network_error_fallback_hmac(self) -> None:
        """api_url configurée, erreur réseau → fallback HMAC. Token HMAC valide → valid=True."""
        client = _client(api_url="https://api.onmci.ci")
        token = _valid_token()

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            result = client.verify(token, _PRESCRIBER)

        assert result.valid is True
        assert result.method == "HMAC_LOCAL"

    def test_verify_with_api_url_network_error_fallback_format(self) -> None:
        """api_url configurée, erreur réseau, HMAC invalide, format hex OK → FORMAT_ONLY, valid=True."""
        client = _client(api_url="https://api.onmci.ci")
        # Token hex valide mais pas le bon HMAC
        token = "b" * 64

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            result = client.verify(token, _PRESCRIBER)

        assert result.valid is True
        assert result.method == "FORMAT_ONLY"

    def test_verify_strips_whitespace(self) -> None:
        """Les espaces en début/fin du token sont ignorés."""
        client = _client(api_url=None)
        token = _valid_token()
        result = client.verify(f"  {token}  ", _PRESCRIBER)
        assert result.valid is True
        assert result.method == "HMAC_LOCAL"


# ---------------------------------------------------------------------------
# 5. ONMCIVerificationResult
# ---------------------------------------------------------------------------


class TestONMCIVerificationResult:
    def test_frozen_dataclass(self) -> None:
        """ONMCIVerificationResult est immuable (frozen=True)."""
        result = ONMCIVerificationResult(
            valid=True,
            method="HMAC_LOCAL",
            prescriber_name=None,
            license_active=None,
            error=None,
        )
        with pytest.raises(Exception):  # noqa: B017
            result.valid = False  # type: ignore[misc]

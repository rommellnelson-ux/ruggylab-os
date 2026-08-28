"""Tests — aucune trace interne ne sort vers le client (`py/stack-trace-exposure`).

Vérifie que les réponses d'erreur ne portent jamais de `Traceback`, de chemin
local, de représentation brute d'exception ni de coordonnées de base de données,
et que la trace complète reste côté serveur avec un identifiant d'incident.
"""

from __future__ import annotations

import logging
import re

import pytest

from app.core.health_check import HealthCheckService

# Marqueurs qui ne doivent JAMAIS apparaître dans une réponse au client.
_MARQUEURS_INTERDITS = (
    "Traceback",
    'File "',
    "site-packages",
    "psycopg",
    "sqlalchemy",
    "OperationalError",
    "ProgrammingError",
    "password",
    "postgresql://",
    "postgresql+psycopg",
    "C:\\",
    "/home/",
    "/usr/lib",
)


def _assert_sans_detail_interne(texte: str) -> None:
    bas = texte.lower()
    for marqueur in _MARQUEURS_INTERDITS:
        assert marqueur.lower() not in bas, f"la réponse expose {marqueur!r} : {texte!r}"


class _BrokenSession:
    """Session dont la requête échoue avec un message très bavard."""

    def execute(self, *_args, **_kwargs):
        raise RuntimeError(
            'connection to server at "db.interne.local" (10.0.0.9), port 5432 failed: '
            'FATAL: password authentication failed for user "ruggylab_prod"'
        )


# ── sonde de santé : le vrai positif ────────────────────────────────────────


def test_database_check_failure_hides_connection_details(caplog):
    service = HealthCheckService(__import__("datetime").datetime.now(__import__("datetime").UTC))

    with caplog.at_level(logging.ERROR, logger="app.core.health_check"):
        ok, payload = service.check_database(_BrokenSession())

    assert ok is False
    assert payload["status"] == "unhealthy"
    _assert_sans_detail_interne(str(payload))
    # Rien de l'exception ne transparaît.
    assert "10.0.0.9" not in str(payload)
    assert "ruggylab_prod" not in str(payload)
    assert "db.interne.local" not in str(payload)


def test_database_check_failure_returns_an_incident_id():
    service = HealthCheckService(__import__("datetime").datetime.now(__import__("datetime").UTC))
    _ok, payload = service.check_database(_BrokenSession())

    incident = payload.get("incident_id")
    assert incident, "un identifiant d'incident doit être fourni au client"
    assert re.fullmatch(r"[0-9a-f]{12}", incident), incident


def test_database_check_failure_keeps_the_trace_server_side(caplog):
    """La trace complète reste dans le journal serveur, corrélée par l'incident."""
    service = HealthCheckService(__import__("datetime").datetime.now(__import__("datetime").UTC))

    with caplog.at_level(logging.ERROR, logger="app.core.health_check"):
        _ok, payload = service.check_database(_BrokenSession())

    assert any(r.exc_info for r in caplog.records), "la trace doit être journalisée"
    assert any(payload["incident_id"] in r.getMessage() for r in caplog.records)


def test_two_failures_get_distinct_incident_ids():
    service = HealthCheckService(__import__("datetime").datetime.now(__import__("datetime").UTC))
    first = service.check_database(_BrokenSession())[1]["incident_id"]
    second = service.check_database(_BrokenSession())[1]["incident_id"]
    assert first != second


def test_readiness_payload_is_free_of_internal_detail():
    service = HealthCheckService(__import__("datetime").datetime.now(__import__("datetime").UTC))
    payload = service.get_readiness(_BrokenSession())
    assert payload["ready"] is False
    _assert_sans_detail_interne(str(payload))


# ── imports en masse : messages reconstruits, jamais propagés ───────────────


def _endpoint_source(nom: str) -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints" / nom
    ).read_text(encoding="utf-8")


def test_bulk_import_handlers_never_propagate_the_exception():
    """Le détail HTTP est construit depuis la contrainte, pas depuis `str(exc)`."""
    for nom in ("bulk_import.py", "registre.py"):
        source = _endpoint_source(nom)
        assert "detail=str(exc)" not in source, f"{nom} propage encore l'exception au client"


def test_http_errors_sever_the_exception_chain():
    """`raise HTTPException(...) from exc` est proscrit dans ces handlers.

    Première correction insuffisante : retirer `str(exc)` du `detail` ne
    suffisait pas — CodeQL a refermé les alertes puis les a rouvertes aux
    nouvelles lignes, car c'est le **chaînage** `from exc` qui fait remonter
    l'exception jusqu'à la réponse dans son modèle. La chaîne est donc coupée
    (`from None`), et la trace journalisée côté serveur.
    """
    import re

    for nom in ("bulk_import.py", "registre.py"):
        # On écarte les commentaires : ils citent `from exc` pour l'expliquer.
        code = "\n".join(
            ligne
            for ligne in _endpoint_source(nom).splitlines()
            if not ligne.lstrip().startswith("#")
        )
        assert not re.search(r"raise HTTPException\([^)]*\)\s*from\s+exc", code, re.S), (
            f"{nom} chaîne encore l'exception vers la réponse HTTP"
        )
        assert "from None" in code, f"{nom} doit couper explicitement la chaîne"


def test_rejected_imports_are_logged_server_side():
    """Couper la chaîne ne doit pas faire perdre l'information : on journalise."""
    for nom, evenement in (
        ("bulk_import.py", "bulk_import.rejected"),
        ("registre.py", "registre_import.rejected"),
    ):
        source = _endpoint_source(nom)
        assert evenement in source, f"{nom} doit journaliser le rejet côté serveur"
        assert "logger" in source


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "endpoint",
    ["/api/v1/bulk-import/patients", "/api/v1/bulk-import/reagents"],
)
def test_oversized_import_returns_a_generic_message(client, endpoint):
    from app.services.bulk_import import MAX_ROWS

    lignes = "\n".join(f"IPP{i},A,B,1990-01-01,F,SGT" for i in range(MAX_ROWS + 5))
    csv = "ipp_unique_id,first_name,last_name,birth_date,sex,rank\n" + lignes

    response = client.post(endpoint, headers=_auth(client), json={"csv": csv, "dry_run": True})

    assert response.status_code == 413, response.text
    detail = response.json()["detail"]
    _assert_sans_detail_interne(detail)
    assert str(MAX_ROWS) in detail, "l'appelant doit connaître la limite applicable"

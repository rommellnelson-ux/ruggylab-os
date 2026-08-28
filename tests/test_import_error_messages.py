"""Tests — les erreurs d'import ne recopient jamais le texte d'une exception.

Les services d'import plaçaient `str(exc)` dans la liste `errors` renvoyée au
client, avec le commentaire « message de validation métier : sûr à exposer ».
Ce n'était pas exact : une `ValidationError` Pydantic contient **la valeur
d'entrée** — donc, pour un import de patients, la donnée patient — ainsi que le
nom du modèle interne.

C'est la source réelle des alertes `py/stack-trace-exposure` #16/#27/#28 : le
flux part de `except … as exc` dans le service et atteint la réponse par la
valeur de retour de l'endpoint. Mes deux corrections précédentes visaient
l'`HTTPException`, qui n'était pas sur ce chemin.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.utils.import_errors import describe_validation_error

# Marqueurs qui trahiraient une recopie du texte d'exception.
_INTERDITS = (
    "validation error",
    "pydantic",
    "https://errors.pydantic.dev",
    "Input should be",
    "type=",
    "input_value",
    "For further information",
    "Traceback",
)


class _Patient(BaseModel):
    ipp_unique_id: str = Field(min_length=3)
    last_name: str = Field(min_length=1)
    birth_date: int = Field(ge=1900)


def _erreur_reelle(**champs) -> ValidationError:
    try:
        _Patient(**champs)
    except ValidationError as exc:
        return exc
    raise AssertionError("le modèle aurait dû échouer")


# ── non-vacuité : l'exception brute FUIT réellement ─────────────────────────


def test_raw_exception_text_would_leak_the_input_value():
    """Preuve que le problème est réel : `str(exc)` contient la valeur saisie.

    Sans ce contrôle, les tests ci-dessous pourraient passer sans rien prouver.
    """
    exc = _erreur_reelle(ipp_unique_id="XY", last_name="DIOMANDE", birth_date=1850)
    brut = str(exc)
    assert "XY" in brut or "1850" in brut, (
        "si l'exception ne portait pas la valeur d'entrée, il n'y aurait rien à corriger"
    )
    assert any(m.lower() in brut.lower() for m in _INTERDITS)


# ── le message construit ne porte rien de tout cela ─────────────────────────


def test_built_message_hides_the_input_value():
    exc = _erreur_reelle(ipp_unique_id="XY", last_name="DIOMANDE", birth_date=1850)
    message = describe_validation_error(exc)
    assert "XY" not in message
    assert "1850" not in message
    assert "DIOMANDE" not in message


def test_built_message_hides_pydantic_internals():
    exc = _erreur_reelle(ipp_unique_id="XY", last_name="", birth_date=1850)
    message = describe_validation_error(exc)
    for marqueur in _INTERDITS:
        assert marqueur.lower() not in message.lower(), f"{marqueur!r} exposé : {message!r}"
    assert "_Patient" not in message, "le nom du modèle interne ne doit pas fuiter"


def test_built_message_still_names_the_faulty_field():
    """Utile à l'opérateur : il doit savoir quelle colonne corriger."""
    exc = _erreur_reelle(ipp_unique_id="XY", last_name="Kone", birth_date=1850)
    message = describe_validation_error(exc)
    assert "birth_date" in message or "ipp_unique_id" in message


def test_built_message_lists_several_problems():
    exc = _erreur_reelle(ipp_unique_id="X", last_name="", birth_date=10)
    message = describe_validation_error(exc)
    assert message.count(":") >= 2, f"les champs fautifs devraient être listés : {message!r}"


def test_plain_value_error_text_is_never_propagated():
    """Le texte d'une `ValueError` vient d'une lib quelconque : jamais propagé."""
    message = describe_validation_error(ValueError("chemin /srv/app/secret.csv illisible"))
    assert "/srv/app/secret.csv" not in message
    assert message == "Ligne rejetée (données invalides)."


@pytest.mark.parametrize(
    "champs",
    [
        {"ipp_unique_id": "AB", "last_name": "K", "birth_date": 1990},
        {"ipp_unique_id": "ABC", "last_name": "", "birth_date": 1990},
        {"ipp_unique_id": "ABC", "last_name": "K", "birth_date": 1000},
    ],
)
def test_message_vocabulary_is_closed(champs):
    """Quelle que soit l'erreur, la sortie reste dans un vocabulaire connu."""
    message = describe_validation_error(_erreur_reelle(**champs))
    assert message.startswith("Ligne rejetée")
    assert message.endswith(".")


# ── plus aucun `str(exc)` dans les services d'import ────────────────────────


def test_services_no_longer_stringify_exceptions():
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "app" / "services"
    for nom in ("bulk_import.py", "registre_import.py"):
        source = (racine / nom).read_text(encoding="utf-8")
        code = "\n".join(x for x in source.splitlines() if not x.lstrip().startswith("#"))
        assert "str(exc)" not in code, f"{nom} recopie encore le texte de l'exception"

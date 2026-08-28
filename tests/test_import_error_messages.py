"""Tests — la réponse d'import ne dérive d'aucun objet exception.

Les services plaçaient `str(exc)` dans la liste `errors` renvoyée au client,
avec le commentaire « message de validation métier : sûr à exposer ». C'était
inexact : une `ValidationError` Pydantic contient le nom du modèle interne, le
chemin du champ, le type d'erreur **et la valeur d'entrée** — donc, pour un
import de patients, la donnée patient elle-même.

C'est la source réelle des alertes `py/stack-trace-exposure` #16/#27/#28 : le
flux part de `except … as exc` dans le service et atteint la réponse par la
valeur de retour de l'endpoint. Deux corrections précédentes visaient
l'`HTTPException`, qui n'est pas sur ce chemin.

Une troisième reconstruisait le message depuis `exc.errors()` : toujours dérivé
de l'objet exception. L'invariant retenu est donc plus strict — **les blocs
`except` de ces services ne lient plus l'exception du tout**, et la réponse ne
peut contenir que des messages d'un catalogue constant.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.utils.import_errors import MESSAGES, message, parse_date, parse_decimal

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES = REPO_ROOT / "app" / "services"
_FICHIERS = ("bulk_import.py", "registre_import.py")


def _code_sans_commentaires(nom: str) -> str:
    source = (SERVICES / nom).read_text(encoding="utf-8")
    return "\n".join(x for x in source.splitlines() if not x.lstrip().startswith("#"))


# ── l'invariant central ─────────────────────────────────────────────────────


@pytest.mark.parametrize("nom", _FICHIERS)
def test_no_except_clause_binds_the_exception(nom):
    """`except … as exc` est proscrit : rien ne peut plus en être dérivé.

    Interdire seulement `str(exc)` était insuffisant — `exc.errors()` passait au
    travers. Interdire la liaison elle-même ferme toute la classe de défauts.
    """
    code = _code_sans_commentaires(nom)
    lie = re.findall(r"except\s+[^\n:]+\s+as\s+(\w+)\s*:", code)
    assert not lie, f"{nom} lie encore l'exception : {lie}"


@pytest.mark.parametrize("nom", _FICHIERS)
def test_no_exception_text_reaches_the_response(nom):
    code = _code_sans_commentaires(nom)
    for interdit in ("str(exc)", ".errors()", "exc.args", "repr(exc)", "format_exc"):
        assert interdit not in code, f"{nom} dérive encore de l'exception ({interdit})"


@pytest.mark.parametrize("nom", _FICHIERS)
def test_error_entries_only_use_the_catalogue(nom):
    """Toute valeur de `errors[].error` vient de `import_message(...)`."""
    code = _code_sans_commentaires(nom)
    appels = re.findall(r'"error":\s*([^}]+)\}', code)
    assert appels, f"{nom} : aucune entrée d'erreur trouvée"
    for appel in appels:
        assert appel.strip().startswith("import_message("), (
            f"{nom} : message d'erreur hors catalogue -> {appel.strip()!r}"
        )


def test_catalogue_is_closed_and_free_of_placeholders():
    """Aucun message ne peut être interpolé : pas de format, pas de f-string."""
    for code, texte in MESSAGES.items():
        assert "{" not in texte and "%" not in texte, f"{code} interpolable : {texte!r}"
        assert texte.startswith("Ligne rejetée")


def test_unknown_code_falls_back_instead_of_raising():
    """Un code inattendu ne doit ni lever, ni faire fuiter un texte imprévu."""
    assert message("code_qui_n_existe_pas") in MESSAGES.values()


# ── validation en amont : elle remplace l'exception ─────────────────────────


@pytest.mark.parametrize(
    "valeur,attendu",
    [
        ("2026-08-28", None),
        ("", "champ_manquant"),
        (None, "champ_manquant"),
        ("32/13/1990", "date_invalide"),
        ("pas une date", "date_invalide"),
        ("1990-13-01", "date_invalide"),
    ],
)
def test_parse_date_returns_a_code_instead_of_raising(valeur, attendu):
    date, code = parse_date(valeur)
    assert code == attendu
    assert (date is None) == (attendu is not None)


@pytest.mark.parametrize(
    "valeur,obligatoire,attendu",
    [
        ("12.5", False, None),
        ("12,5", False, None),
        ("", False, None),
        ("", True, "champ_manquant"),
        ("abc", False, "nombre_invalide"),
    ],
)
def test_parse_decimal_returns_a_code_instead_of_raising(valeur, obligatoire, attendu):
    _, code = parse_decimal(valeur, obligatoire=obligatoire)
    assert code == attendu


def test_prevalidation_never_raises_on_hostile_input():
    """Aucune entrée ne doit provoquer d'exception : c'est tout l'intérêt."""
    for valeur in ("", " ", "\x00", "9" * 500, "2026-02-30", "--", "1e400"):
        parse_date(valeur)
        parse_decimal(valeur)


# ── bout en bout : la réponse HTTP ne porte rien de l'entrée ────────────────


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_invalid_rows_never_echo_the_submitted_data(client):
    """Une date impossible et un IPP manquant : la réponse ne renvoie ni l'un ni l'autre."""
    csv = (
        "ipp_unique_id,first_name,last_name,birth_date,sex,rank\n"
        "SECRET-IPP-001,Awa,Kone,32/13/1990,F,Sergent\n"
        ",Yao,Brou,1985-11-03,M,Caporal\n"
    )
    reponse = client.post(
        "/api/v1/bulk-import/patients", headers=_auth(client), json={"csv": csv, "dry_run": True}
    )
    assert reponse.status_code == 200, reponse.text
    corps = reponse.text

    # Ni la valeur fautive, ni les internes de Pydantic.
    assert "32/13/1990" not in corps
    assert "SECRET-IPP-001" not in corps
    for marqueur in ("validation error", "Input should be", "pydantic", "type=", "PatientCreate"):
        assert marqueur.lower() not in corps.lower(), f"{marqueur!r} exposé"

    erreurs = reponse.json()["errors"]
    assert len(erreurs) == 2
    for entree in erreurs:
        assert entree["error"] in MESSAGES.values(), entree


def test_operator_still_learns_why_the_row_failed(client):
    """Le durcissement ne doit pas rendre le rapport inutilisable."""
    csv = (
        "ipp_unique_id,first_name,last_name,birth_date,sex,rank\n"
        "IMP-OK-1,Awa,Kone,32/13/1990,F,Sergent\n"
    )
    reponse = client.post(
        "/api/v1/bulk-import/patients", headers=_auth(client), json={"csv": csv, "dry_run": True}
    )
    erreur = reponse.json()["errors"][0]["error"]
    assert erreur == MESSAGES["date_invalide"]
    assert "date" in erreur.lower(), "l'opérateur doit savoir quelle nature d'erreur corriger"

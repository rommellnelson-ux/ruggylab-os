"""Tests — la version est déclarée au même endroit partout.

Avant ce verrouillage, quatre sources se contredisaient : `pyproject.toml`
disait `0.1.0`, `app/core/config.py` `0.1.0`, `.env.example` `0.7.4`, et le
dernier tag publié était `v0.7.4`. Une image se serait donc annoncée `0.1.0`
tout en portant le code de la `0.8.0`.

`app/core/version.py` est désormais la source unique ; tout le reste en dérive
ou est vérifié ici.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from app.core.version import GIT_TAG, IS_PRERELEASE, PEP440_VERSION, VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ── les quatre écritures désignent la même version ──────────────────────────


def test_public_version_is_semver_with_prerelease():
    assert re.fullmatch(r"\d+\.\d+\.\d+-(alpha|beta|rc)\.\d+", VERSION), VERSION


def test_git_tag_derives_from_the_public_version():
    assert GIT_TAG == f"v{VERSION}"


def test_prerelease_flag_matches_the_suffix():
    assert IS_PRERELEASE is ("-" in VERSION)


def test_pep440_and_public_version_describe_the_same_release():
    """`0.8.0-beta.1` et `0.8.0b1` doivent désigner la même version.

    PEP 440 n'admet pas le tiret ; la correspondance est donc calculée, pas
    supposée — sans quoi on pourrait publier `0.8.0b1` du paquet et annoncer
    `0.9.0-beta.1` dans l'API.
    """
    correspondances = {"alpha": "a", "beta": "b", "rc": "rc"}
    base, suffixe = VERSION.split("-", 1)
    genre, numero = suffixe.rsplit(".", 1)
    attendu = f"{base}{correspondances[genre]}{numero}"
    assert PEP440_VERSION == attendu, f"{PEP440_VERSION} != {attendu}"


# ── chaque déclaration du dépôt suit la source unique ───────────────────────


def test_pyproject_version_matches(pyproject):
    assert pyproject["project"]["version"] == PEP440_VERSION


def test_pyproject_declares_beta_maturity(pyproject):
    classifiers = pyproject["project"]["classifiers"]
    maturites = [c for c in classifiers if c.startswith("Development Status")]
    assert maturites == ["Development Status :: 4 - Beta"], maturites


def test_api_version_matches():
    """La version servie par l'API et par OpenAPI vient de la source unique."""
    from app.core.config import settings

    assert settings.APP_VERSION == VERSION


def test_openapi_advertises_the_same_version():
    from app.main import app

    assert app.version == VERSION


def test_env_example_matches():
    raw = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    ligne = next(x for x in raw.splitlines() if x.startswith("APP_VERSION="))
    assert ligne.split("=", 1)[1].strip() == VERSION


def test_docker_image_label_matches():
    raw = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    trouve = re.search(r'org\.opencontainers\.image\.version="([^"]+)"', raw)
    assert trouve is not None, "le label OCI de version est absent"
    assert trouve.group(1) == VERSION


def test_dockerfile_label_block_is_not_broken():
    """Régression : un `\\n` littéral avait cassé la continuation du LABEL."""
    raw = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    for ligne in raw.splitlines():
        assert "\\n" not in ligne, f"continuation cassée : {ligne!r}"


# ── le CHANGELOG porte bien cette version ───────────────────────────────────


def _changelog() -> str:
    return (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_changelog_has_an_entry_for_this_version():
    assert f"## [{VERSION}]" in _changelog(), (
        f"aucune section CHANGELOG pour {VERSION} : une version sans entrée "
        "est une version dont personne ne sait ce qu'elle contient"
    )


def test_changelog_entry_is_dated():
    trouve = re.search(rf"## \[{re.escape(VERSION)}\] - (\d{{4}}-\d{{2}}-\d{{2}})", _changelog())
    assert trouve is not None, "la section doit porter une date ISO"


def test_changelog_keeps_an_unreleased_section():
    assert "## [Non publié]" in _changelog()


def test_changelog_entry_carries_the_clinical_warning():
    """Une bêta ne doit jamais être lue comme utilisable en clinique."""
    contenu = _changelog()
    section = contenu.split(f"## [{VERSION}]", 1)[1]
    assert "REAL_DATA_NO_GO" in section
    assert "désactivées par défaut" in section


def test_changelog_entry_documents_limits_and_rollback():
    section = _changelog().split(f"## [{VERSION}]", 1)[1]
    for titre in (
        "### Sécurité",
        "### Migrations",
        "### Configuration",
        "### Limites connues",
        "### Rollback",
    ):
        assert titre in section, f"section manquante : {titre}"


# ── cohérence avec le pipeline de release ───────────────────────────────────


def test_tag_would_be_accepted_by_the_release_guard():
    """Le tag prévu doit passer la validation de forme du workflow."""
    pre = r"^v\d+\.\d+\.\d+-(alpha|beta|rc)\.\d+$"
    stable = r"^v\d+\.\d+\.\d+$"
    assert re.match(pre, GIT_TAG) or re.match(stable, GIT_TAG)


def test_prerelease_tag_is_required_while_no_go():
    """Sous REAL_DATA_NO_GO, la version prévue ne peut pas être stable."""
    fichier = REPO_ROOT / "docs" / "governance" / "CLINICAL_STATUS"
    if not fichier.is_file():
        # Introduit par la PR du pipeline de release ; ce test s'active dès
        # qu'elle est fusionnée.
        pytest.skip("docs/governance/CLINICAL_STATUS pas encore présent")
    if fichier.read_text(encoding="utf-8").strip() == "REAL_DATA_NO_GO":
        assert IS_PRERELEASE, (
            "le statut clinique interdit une version stable : "
            f"{VERSION} devrait porter un suffixe alpha/beta/rc"
        )

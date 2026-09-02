"""Tests — l'audit du SBOM ne peut pas accepter une licence indéterminée.

L'inventaire Python ne couvre que les distributions Python. L'image embarque en
plus toute la base système, et c'est l'image que l'on distribue. Ce contrôle a
fait apparaître la base Debian de `python:3.13-slim` : 87 paquets, majoritairement
sous GPL/LGPL, traités au §6.4 de `THIRD_PARTY_NOTICES.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_sbom_licenses import auditer

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRE = REPO_ROOT / "docs" / "governance" / "SBOM_LICENSE_EXCEPTIONS.json"


@pytest.fixture(scope="module")
def registre() -> dict:
    return json.loads(REGISTRE.read_text(encoding="utf-8"))


def _sbom(*composants: dict) -> dict:
    return {"components": list(composants)}


def _mit(nom: str, version: str = "1.0") -> dict:
    return {
        "type": "library",
        "name": nom,
        "version": version,
        "licenses": [{"license": {"id": "MIT"}}],
    }


def test_a_component_without_a_license_fails(registre):
    inconnus, _ = auditer(_sbom({"type": "library", "name": "opaque", "version": "1.0"}), registre)
    assert [c["name"] for c in inconnus] == ["opaque"]


def test_a_qualified_exception_passes(registre):
    entree = registre["exceptions"][0]
    inconnus, _ = auditer(
        _sbom({"type": "library", "name": entree["name"], "version": entree["version"]}),
        registre,
    )
    assert inconnus == []


def test_an_exception_does_not_cover_another_version(registre):
    """Une décision porte sur une version précise, pas sur un nom."""
    entree = registre["exceptions"][0]
    inconnus, _ = auditer(
        _sbom({"type": "library", "name": entree["name"], "version": "99.99"}), registre
    )
    assert len(inconnus) == 1


def test_file_entries_are_not_third_party_components(registre):
    """Le SBOM catalogue ~2 800 fichiers : ce ne sont pas des composants."""
    inconnus, _ = auditer(_sbom({"type": "file", "name": "/app/x.py", "version": ""}), registre)
    assert inconnus == []


def test_copyleft_families_are_counted(registre):
    _, familles = auditer(
        _sbom(
            _mit("a"),
            {
                "type": "library",
                "name": "b",
                "version": "1",
                "licenses": [{"license": {"id": "GPL-2.0-only"}}],
            },
            {
                "type": "library",
                "name": "c",
                "version": "1",
                "licenses": [{"expression": "LGPL-2.1-or-later"}],
            },
        ),
        registre,
    )
    assert familles["GPL-2.0-only"] == 1
    assert familles["LGPL-2.1-or-later"] == 1
    assert "MIT" not in familles, "le recensement porte sur le copyleft, pas sur tout"


# ── le registre est un registre de décisions, pas une liste de noms ─────────


@pytest.mark.parametrize("champ", ["constat", "qualification", "decision", "date", "portee"])
def test_every_exception_is_a_written_dated_decision(registre, champ):
    for entree in registre["exceptions"]:
        valeur = entree.get(champ, "")
        assert valeur and len(valeur) > 3, (
            f"exception {entree.get('name')!r} : champ {champ!r} vide — "
            "une licence indéterminée ne peut pas être acceptée sans motif écrit"
        )


def test_the_base_image_finding_is_recorded(registre):
    """Le §6.4 doit rester ouvert tant que l'offre de source n'est pas instruite."""
    notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "BASE_IMAGE_SOURCE_OFFER_REVIEW_REQUIRED" in notices
    assert "ne rend pas RUGGYLAB OS open source" in notices
    assert "87 paquets Debian" in notices


def test_no_conclusion_is_drawn_without_evidence():
    """Ni compatibilité ni incompatibilité n'est affirmée sur les points ouverts."""
    notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "elle n'a pas été instruite" in notices
    assert "REVUE OBLIGATOIRE — §6.4" in notices

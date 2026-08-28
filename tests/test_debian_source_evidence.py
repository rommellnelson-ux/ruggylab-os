"""Tests — la base est épinglée, et les preuves de source sont exigibles.

`3.13-slim` était un tag FLOTTANT : il suit les correctifs et change de contenu
sans prévenir. Une release construite dessus n'est pas reproductible, et les
preuves rassemblées ne décrivent plus l'image livrée. Ces tests empêchent d'y
revenir, et vérifient que rien n'est conclu juridiquement sans validation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from scripts.debian_source_manifest import (
    _REFERENCE_LICENCE,
    _defauts_qualifies,
    _licence_du_copyright,
    paquets_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_DIGEST = "sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f"
REGISTRE = REPO_ROOT / "docs" / "governance" / "DEBIAN_NOTICE_EXCEPTIONS.json"
CONFORMITE = "docs/compliance/SOURCE_COMPLIANCE.md"
MODELE_OFFRE = "docs/compliance/SOURCE_OFFER_TEMPLATE.md"

#: Une base épinglée : version exacte, puis digest.
_BASE_EPINGLEE = re.compile(
    r"^FROM python:\d+\.\d+\.\d+-slim[a-z-]*@sha256:[0-9a-f]{64}", re.MULTILINE
)


def _lire(chemin: str) -> str:
    return (REPO_ROOT / chemin).read_text(encoding="utf-8")


def _phrase(chemin: str) -> str:
    """Contenu sans mise en page : les phrases sont enveloppées sur plusieurs
    lignes et portent des marqueurs Markdown. On compare le propos, pas sa
    présentation."""
    return " ".join(_lire(chemin).replace("*", "").replace(">", " ").split())


# ── la base ne peut plus flotter ────────────────────────────────────────────


def test_every_base_stage_is_pinned_by_version_and_digest():
    dockerfile = _lire("Dockerfile")
    etapes = [ligne for ligne in dockerfile.splitlines() if ligne.startswith("FROM python:")]
    assert etapes, "aucune étape ne part d'une image Python"
    for etape in etapes:
        assert _BASE_EPINGLEE.match(etape), f"base non épinglée : {etape}"


def test_the_two_stages_use_the_same_base():
    """Deux bases différentes produiraient un binaire et des preuves discordants."""
    bases = {
        ligne.split()[1]
        for ligne in _lire("Dockerfile").splitlines()
        if ligne.startswith("FROM python:")
    }
    assert len(bases) == 1, f"étapes sur des bases différentes : {bases}"
    assert BASE_DIGEST in bases.pop()


def test_no_floating_base_tag_remains():
    for flottant in ("FROM python:3.13-slim", "FROM python:3-slim", "FROM python:latest"):
        assert flottant not in _lire("Dockerfile"), f"tag flottant réintroduit : {flottant}"


# ── le relevé des références de licence ne se laisse pas piéger ─────────────


def test_a_trailing_full_stop_is_not_part_of_the_licence_name():
    """« voir /usr/share/common-licenses/GPL-2. » désigne GPL-2, pas « GPL-2. »."""
    texte = "the complete text can be found in /usr/share/common-licenses/GPL-2."
    assert _REFERENCE_LICENCE.findall(texte) == ["GPL-2"]


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("in `/usr/share/common-licenses/GPL-3'.", ["GPL-3"]),
        ("see /usr/share/common-licenses/LGPL-2.1’.", ["LGPL-2.1"]),
        ("/usr/share/common-licenses/GPL',", ["GPL"]),
        ("/usr/share/common-licenses/Apache-2.0 applies", ["Apache-2.0"]),
    ],
)
def test_licence_references_survive_surrounding_punctuation(texte, attendu):
    assert _REFERENCE_LICENCE.findall(texte) == attendu


def test_dep5_licence_fields_are_preferred_over_references():
    copyright_dep5 = "Files: *\nLicense: GPL-2+\n\nLicense: GPL-2+\n Full text…\n"
    assert _licence_du_copyright(copyright_dep5) == ["GPL-2+"]


def test_free_form_copyright_falls_back_to_the_referenced_texts():
    libre = "See /usr/share/common-licenses/GPL-3 for the full text."
    assert _licence_du_copyright(libre) == ["référencée:GPL-3"]


# ── le regroupement par paquet source ───────────────────────────────────────


def test_binaries_are_grouped_under_their_source_package():
    binaires = [
        {
            "binary_package": "libattr1",
            "version": "1",
            "source_package": "attr",
            "source_version": "2",
        },
        {"binary_package": "attr", "version": "1", "source_package": "attr", "source_version": "2"},
    ]
    manifeste = [
        {
            "binary_package": "libattr1",
            "copyleft_licenses": ["GPL-2+"],
            "source_offer_obligation": True,
        },
        {"binary_package": "attr", "copyleft_licenses": [], "source_offer_obligation": False},
    ]
    groupes = paquets_sources(binaires, manifeste)
    assert len(groupes) == 1
    groupe = groupes[0]
    assert groupe["produces_binaries"] == ["attr", "libattr1"]
    assert groupe["source_offer_obligation"] is True, "un seul binaire copyleft suffit"
    assert groupe["snapshot_source_url"].startswith("https://snapshot.debian.org/package/attr/2")


def test_availability_starts_as_unverified():
    """Tant que l'URL n'a pas été ouverte, elle ne prouve rien."""
    groupes = paquets_sources(
        [{"binary_package": "x", "version": "1", "source_package": "x", "source_version": "1"}],
        [{"binary_package": "x", "copyleft_licenses": [], "source_offer_obligation": False}],
    )
    assert groupes[0]["source_availability"] == "à vérifier"


# ── le registre des défauts de notice est un registre de décisions ──────────


@pytest.fixture(scope="module")
def registre() -> dict:
    return json.loads(REGISTRE.read_text(encoding="utf-8"))


def test_the_gzip_notice_defect_is_qualified(registre):
    qualifies = _defauts_qualifies(REGISTRE)
    assert ("gzip", "GFDL-3") in qualifies


@pytest.mark.parametrize("champ", ["constat", "qualification", "portee", "decision", "date"])
def test_every_notice_exception_is_written_and_dated(registre, champ):
    for entree in registre["exceptions"]:
        valeur = entree.get(champ, "")
        assert valeur and len(valeur) > 3, (
            f"{entree.get('binary_package')!r} : champ {champ!r} vide — "
            "un défaut de notice ne s'accepte pas sans motif écrit"
        )


def test_an_unqualified_defect_is_not_silently_accepted():
    qualifies = _defauts_qualifies(REGISTRE)
    assert ("tar", "GPL-9") not in qualifies


def test_a_missing_register_qualifies_nothing():
    """Supprimer le registre ne doit pas faire disparaître les défauts."""
    assert _defauts_qualifies(REPO_ROOT / "docs" / "governance" / "inexistant.json") == set()


# ── rien n'est conclu juridiquement ─────────────────────────────────────────


def test_the_compliance_document_claims_no_conformity():
    contenu = _lire(CONFORMITE)
    assert "Ce document ne déclare aucune conformité" in contenu
    assert "LEGAL_SOURCE_OFFER_REVIEW_REQUIRED" in contenu
    assert "BASE_IMAGE_SOURCE_EVIDENCE_PREPARED" in contenu


def test_the_compliance_document_does_not_overstate_the_gpl():
    """La présence de paquets GPL dans une base n'ouvre pas le code de RUGGYLAB."""
    assert "ne rend RUGGYLAB OS open source" in _phrase(CONFORMITE)


def test_the_four_options_are_prepared_without_a_choice():
    contenu = _phrase(CONFORMITE)
    for option in (
        "A. Bundle",
        "B. Téléchargement reproductible",
        "C. Offre écrite",
        "D. Conservation",
    ):
        assert option in contenu, f"option absente : {option}"
    assert "sans qu'aucune soit retenue" in contenu


def test_the_source_offer_template_is_not_signed():
    contenu = _lire(MODELE_OFFRE)
    assert "MODÈLE — NON SIGNÉ, NON DÉLIVRÉ, NON RETENU" in contenu
    for ligne in contenu.splitlines():
        depouille = ligne.strip()
        if depouille.startswith(("Nom :", "Qualité :", "Date :", "Signature :")):
            assert depouille.endswith(":"), f"champ pré-rempli : {depouille!r}"


def test_the_offer_template_requires_a_digest_not_a_tag():
    assert "Une offre qui ne désigne pas un digest ne désigne rien" in _phrase(MODELE_OFFRE)


def test_the_offer_template_excludes_ruggylab_own_code():
    assert "aucune obligation d'ouverture du code de RUGGYLAB OS" in _phrase(MODELE_OFFRE)


# ── la CI produit les preuves ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(_lire(".github/workflows/ci.yml"))


def test_the_evidence_job_exists_and_builds_the_real_image(ci):
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    noms = [str(s.get("name", "")) for s in etapes]
    assert "Build the image whose packages will be inventoried" in noms
    assert "Assert the base image is pinned by digest" in noms


def test_the_evidence_job_actually_opens_the_source_urls(ci):
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    generation = next(s for s in etapes if "Generate the Debian source" in str(s.get("name", "")))
    assert "--check-availability" in generation["run"]
    controle = next(s for s in etapes if "reachable" in str(s.get("name", "")))
    assert "indisponible:" in controle["run"]


def test_the_evidence_is_published_as_an_artifact(ci):
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    publication = next(
        s for s in etapes if str(s.get("uses", "")).startswith("actions/upload-artifact")
    )
    chemins = publication["with"]["path"]
    for fichier in (
        "debian-binary-packages.json",
        "debian-source-packages.json",
        "debian-license-manifest.json",
    ):
        assert fichier in chemins, f"{fichier} n'est pas publié"


# ── invariants ──────────────────────────────────────────────────────────────


def test_clinical_invariants_are_untouched():
    config = _lire("app/core/config.py")
    for reglage in (
        "CSA_SYNC_ENABLED: bool = False",
        "ENABLE_DH36_LISTENER: bool = False",
        "ANALYZER_RAW_LISTENER_ENABLED: bool = False",
    ):
        assert reglage in config
    assert _lire("docs/governance/CLINICAL_STATUS").strip() == "REAL_DATA_NO_GO"

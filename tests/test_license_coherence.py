"""Tests — la licence dit la même chose partout, et rien de faux.

Le dépôt déclarait GPL-2.0 à trois endroits sans contenir de fichier `LICENSE` :
une assertion de licence sans son texte, juridiquement vide et trompeuse. Ces
tests empêchent d'y retomber, dans un sens comme dans l'autre.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

LICENSE_REF = "LicenseRef-RuggyLab-Evaluation-1.0"
TITULAIRE = "WOGNIN Nelson Rommell Boni Ruggairrhye"

#: Fichiers qui portent une déclaration de licence active.
_DECLARATIONS = ("pyproject.toml", "Dockerfile", "README.md", "LICENSE.md")

#: Documents d'audit : ils citent l'ancien état à dessein, et doivent le garder.
_HISTORIQUES = {
    "docs/governance/LICENSE_DECISION_REQUIRED.md",
    "docs/governance/LICENSE_RECOMMENDATION_BETA_2026-08-28.md",
    "docs/governance/LICENSE_DECISION_BETA_2026-08-28.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
}


def _lire(chemin: str) -> str:
    return (REPO_ROOT / chemin).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(_lire("pyproject.toml"))


# ── le fichier de licence existe et nomme le bon titulaire ──────────────────


def test_license_file_exists():
    assert (REPO_ROOT / "LICENSE.md").is_file(), (
        "déclarer une licence sans en fournir le texte ne vaut rien"
    )


def test_license_names_the_rights_holder():
    texte = _lire("LICENSE.md")
    assert f"Copyright © 2026 {TITULAIRE}." in texte
    assert "Tous droits réservés." in texte


def test_license_declares_its_identifier():
    assert LICENSE_REF in _lire("LICENSE.md")


# ── aucune autre personne n'est créditée comme titulaire ────────────────────
#
# Contrôle par LISTE BLANCHE, et non par liste noire : on vérifie que le seul
# nom en capitales apparaissant dans les fichiers de licence et de gouvernance
# est celui du titulaire. C'est plus fort qu'interdire un nom précis — et cela
# évite d'inscrire dans le dépôt le nom qu'on cherche justement à en exclure.

_FICHIERS_TITULARITE = (
    "LICENSE.md",
    "docs/governance/LICENSE_DECISION_BETA_2026-08-28.md",
    "docs/governance/LICENSE_RECOMMENDATION_BETA_2026-08-28.md",
)

#: Lignes qui attribuent des droits à quelqu'un.
_LIGNES_TITULARITE = re.compile(
    r"^.*(Copyright|[Tt]itulaire|[Aa]uteur|image\.authors).*$", re.MULTILINE
)

#: Un patronyme est repéré par sa forme : CAPITALES suivies d'un prénom capitalisé.
_PATRONYME = re.compile(r"\b([A-ZÀ-Ý]{3,})\s+[A-ZÀ-Ý][a-zà-ÿ]+")


@pytest.mark.parametrize("chemin", _FICHIERS_TITULARITE)
def test_no_unexpected_person_is_credited(chemin):
    """Seul le titulaire autorisé peut être nommé sur une ligne de titularité.

    Contrôle restreint aux lignes qui **attribuent** des droits : y chercher un
    patronyme est précis, alors que balayer toutes les capitales du document
    remonterait surtout des mots français mis en emphase.
    """
    attendu = TITULAIRE.split()[0]
    for ligne in _LIGNES_TITULARITE.findall(_lire(chemin)):
        for patronyme in _PATRONYME.findall(ligne):
            assert patronyme == attendu, (
                f"{chemin} : une autre personne semble créditée — {patronyme!r} dans {ligne.strip()!r}"
            )


@pytest.mark.parametrize("chemin", _FICHIERS_TITULARITE)
def test_the_authorised_holder_is_actually_named(chemin):
    """Le contrôle ci-dessus serait vide si aucun titulaire n'était nommé."""
    assert TITULAIRE in _lire(chemin), f"{chemin} ne nomme pas le titulaire"


# ── plus aucune déclaration GPL-2.0 active pour RUGGYLAB ────────────────────


@pytest.mark.parametrize("chemin", _DECLARATIONS)
def test_no_active_gpl_declaration(chemin):
    contenu = _lire(chemin)
    for motif in ("GPL-2.0", "GPLv2", "General Public License"):
        assert motif not in contenu, f"{chemin} déclare encore {motif}"


def test_historical_audit_documents_are_preserved():
    """Les constats historiques gardent la mention d'origine : ils la décrivent."""
    contenu = _lire("docs/governance/LICENSE_DECISION_REQUIRED.md")
    assert "GPL-2.0" in contenu, "le constat initial ne doit pas être réécrit"
    assert "décision de principe PRISE" in contenu, "la mise à jour doit être visible"


# ── le LicenseRef est identique partout ─────────────────────────────────────


def test_pyproject_uses_the_license_ref(pyproject):
    assert pyproject["project"]["license"] == LICENSE_REF


def test_pyproject_has_no_osi_classifier(pyproject):
    """`License :: OSI Approved` est réservé aux licences approuvées par l'OSI."""
    osi = [c for c in pyproject["project"]["classifiers"] if c.startswith("License ::")]
    assert not osi, f"classifier de licence OSI interdit ici : {osi}"


def test_pyproject_declares_license_files(pyproject):
    fichiers = pyproject["project"]["license-files"]
    assert "LICENSE.md" in fichiers
    assert "THIRD_PARTY_NOTICES.md" in fichiers
    assert any("licenses/third-party" in f for f in fichiers)


def test_build_backend_supports_pep639(pyproject):
    """setuptools < 77.0.3 ignorerait `license` et `license-files` en silence."""
    requires = " ".join(pyproject["build-system"]["requires"])
    trouve = re.search(r"setuptools>=(\d+)\.(\d+)\.?(\d*)", requires)
    assert trouve, requires
    majeur, mineur, patch = (int(trouve.group(i) or 0) for i in (1, 2, 3))
    assert (majeur, mineur, patch) >= (77, 0, 3), f"setuptools trop ancien : {trouve.group(0)}"


def test_dockerfile_uses_the_license_ref():
    contenu = _lire("Dockerfile")
    assert f'org.opencontainers.image.licenses="{LICENSE_REF}"' in contenu
    assert f'org.opencontainers.image.authors="{TITULAIRE}"' in contenu


def test_readme_announces_the_proprietary_licence():
    contenu = _lire("README.md")
    assert "Proprietary%20Evaluation" in contenu, "le badge doit refléter la licence réelle"
    assert LICENSE_REF in contenu
    assert TITULAIRE in contenu


# ── l'image embarque les fichiers de licence ────────────────────────────────


def test_dockerfile_copies_licence_files_into_the_image():
    contenu = _lire("Dockerfile")
    for cible in ("LICENSE.md", "THIRD_PARTY_NOTICES.md", "licenses/third-party/"):
        assert cible in contenu, f"{cible} n'est pas copié dans l'image"
    assert "--chmod=0444" in contenu, "les licences doivent être en lecture seule"


# ── notices tierces ─────────────────────────────────────────────────────────


def test_third_party_notices_exist():
    assert (REPO_ROOT / "THIRD_PARTY_NOTICES.md").is_file()


def test_third_party_licence_texts_are_versioned():
    base = REPO_ROOT / "licenses" / "third-party" / "python"
    paquets = [p for p in base.iterdir() if p.is_dir()] if base.is_dir() else []
    assert len(paquets) >= 15, (
        f"seulement {len(paquets)} textes de licence versionnés — le build de l'image "
        "les copie, ils doivent être présents dans le dépôt"
    )


def test_notices_state_that_third_parties_are_not_covered():
    contenu = _lire("THIRD_PARTY_NOTICES.md")
    assert "ne sont PAS couverts" in contenu
    assert "licenses/third-party/" in contenu


def test_components_under_manual_review_are_flagged():
    """Redis 7.4 et Grafana 11 doivent rester signalés tant qu'ils ne sont pas tranchés."""
    contenu = _lire("THIRD_PARTY_NOTICES.md")
    assert "MANUAL_LICENSE_REVIEW_REQUIRED" in contenu
    assert "AGPL_DISTRIBUTION_REVIEW_REQUIRED" in contenu
    for composant in ("Redis 7.4", "Grafana 11"):
        assert composant in contenu, f"{composant} doit figurer au registre des décisions"


def test_lgpl_obligation_is_not_overstated():
    """Ne pas laisser croire que la LGPL rendrait RUGGYLAB open source."""
    contenu = _lire("THIRD_PARTY_NOTICES.md")
    assert "La LGPL ne rend pas RUGGYLAB OS open source" in contenu


# ── gouvernance : rien n'est signé, rien n'est simulé ───────────────────────


def test_decision_document_leaves_the_signature_blank():
    contenu = _lire("docs/governance/LICENSE_DECISION_BETA_2026-08-28.md")
    assert "Nom du décideur :" in contenu
    for ligne in contenu.splitlines():
        depouille = ligne.strip()
        if depouille.startswith(("Nom du décideur :", "Date :", "Signature :")):
            assert depouille.endswith(":"), f"champ pré-rempli : {depouille!r}"


def test_decision_document_records_the_holder_and_the_evaluation_site():
    contenu = _lire("docs/governance/LICENSE_DECISION_BETA_2026-08-28.md")
    assert TITULAIRE in contenu
    assert "site d'évaluation" in contenu
    assert "aucun droit de propriété" in contenu


# ── invariants cliniques préservés ──────────────────────────────────────────


def test_clinical_status_is_unchanged():
    statut = _lire("docs/governance/CLINICAL_STATUS").strip()
    assert statut == "REAL_DATA_NO_GO"


def test_licence_forbids_real_clinical_use():
    contenu = _lire("LICENSE.md")
    assert "REAL_DATA_NO_GO" in contenu
    for interdiction in (
        "utilisation clinique réelle",
        "patients réels",
        "déploiement de production",
    ):
        assert interdiction in contenu, f"interdiction absente : {interdiction}"


def test_csa_sync_and_analyzers_remain_disabled():
    config = _lire("app/core/config.py")
    for reglage in (
        "CSA_SYNC_ENABLED: bool = False",
        "ENABLE_DH36_LISTENER: bool = False",
        "ANALYZER_RAW_LISTENER_ENABLED: bool = False",
    ):
        assert reglage in config, f"réglage modifié : {reglage}"


def test_licence_defers_clauses_needing_legal_review():
    """Ne pas prétendre trancher ce qui exige un juriste."""
    contenu = _lire("LICENSE.md")
    assert "Clauses à valider avant distribution externe" in contenu
    assert "n'est pas un avis juridique" in contenu

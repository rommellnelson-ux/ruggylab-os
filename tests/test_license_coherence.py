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
    "docs/governance/EVALUATION_AUTHORIZATION_CSA_GR_PLATEAU_TEMPLATE.md",
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


def test_licence_directories_stay_traversable():
    """`--chmod=0444` sur une arborescence rend les répertoires intraversables.

    Les textes seraient présents dans l'image mais illisibles pour l'utilisateur
    du conteneur — une notice qu'on ne peut pas lire ne vaut pas notice. Le mode
    est donc posé par type, après la copie.
    """
    contenu = _lire("Dockerfile")
    copie = next(
        ligne
        for ligne in contenu.splitlines()
        if ligne.startswith("COPY") and "licenses/third-party/" in ligne
    )
    assert "--chmod" not in copie, "un mode unique casserait la traversée des répertoires"
    assert "-type d -exec chmod 0555" in contenu
    assert "-type f -exec chmod 0444" in contenu


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


def test_dockerignore_does_not_exclude_the_licence_files():
    """`*.md` les excluait en silence : le build echouait, mais seulement en CI."""
    contenu = _lire(".dockerignore")
    for exception in ("!LICENSE.md", "!THIRD_PARTY_NOTICES.md", "!licenses/"):
        assert exception in contenu, (
            f"{exception} absent : le contexte de build n'inclura pas les licences"
        )


# ── décisions de distribution : durée, site, dépôt privé ────────────────────

_MODELE_AUTORISATION = "docs/governance/EVALUATION_AUTHORIZATION_CSA_GR_PLATEAU_TEMPLATE.md"
_CHECKLIST_PRIVE = "docs/governance/PRIVATE_REPOSITORY_PRE_TAG_CHECKLIST.md"


def test_evaluation_duration_is_recorded_and_not_renewable():
    """Six mois, sans reconduction tacite : ce n'est plus une question ouverte."""
    licence = _lire("LICENSE.md")
    assert "maximale de six (6) mois" in licence
    assert "n'est pas renouvelée automatiquement" in licence
    assert "autorisation écrite distincte" in licence


def test_duration_is_no_longer_listed_as_an_open_clause():
    """Le §12 listait la durée comme non arrêtée ; elle l'est désormais."""
    clauses = _lire("LICENSE.md").split("## 12.")[1].split("## 13.")[0]
    assert "n'est plus en discussion" in clauses


@pytest.mark.parametrize(
    "cas",
    [
        "Remplacement par une nouvelle version",
        "Retrait pour raison de sécurité",
        "Violation des conditions d'évaluation",
        "Décision du Titulaire",
        "Modification du statut de gouvernance",
    ],
)
def test_early_termination_cases_are_enumerated(cas):
    assert cas in _lire("LICENSE.md"), f"cas de cessation absent : {cas}"


def test_the_authorisation_template_is_not_signed():
    """Un modèle pré-rempli serait une signature simulée."""
    contenu = _lire(_MODELE_AUTORISATION)
    assert "MODÈLE — NON SIGNÉ, NON DÉLIVRÉ" in contenu
    for ligne in contenu.splitlines():
        depouille = ligne.strip()
        if depouille.startswith(("Nom :", "Qualité :", "Date :", "Signature :")):
            assert depouille.endswith(":"), f"champ pré-rempli : {depouille!r}"


def test_the_authorisation_template_states_the_site_holds_no_rights():
    contenu = _lire(_MODELE_AUTORISATION)
    assert "Centre de Santé des Armées de la Garde Républicaine du Plateau" in contenu
    assert "ne détient aucun droit de propriété" in contenu
    assert TITULAIRE in contenu
    for exigence in (
        "six (6) mois",
        "fictives ou synthétiques",
        "REAL_DATA_NO_GO",
        "Interdiction de redistribution",
        "Résiliation anticipée",
    ):
        assert exigence in contenu, f"exigence absente du modèle : {exigence}"


def test_the_private_repository_checklist_blocks_tagging():
    contenu = _lire(_CHECKLIST_PRIVE)
    assert "INTERDICTION DE TAGUER" in contenu
    for verification in (
        "Bundle Git complet",
        "forks publics",
        "collaborateurs",
        "Aucun secret dans l'historique",
        "Quota GitHub Actions",
        "CodeQL",
        "GHCR",
        "Relancer l'intégralité de la CI",
        "Rollback",
    ):
        assert verification in contenu, f"vérification absente : {verification}"


def test_repository_visibility_is_not_claimed_to_have_changed():
    contenu = _lire(_CHECKLIST_PRIVE)
    assert "Visibilité actuelle | **publique — inchangée**" in contenu


# ── décisions Redis et Grafana : prises, mais pas encore mises en œuvre ─────


def test_redis_and_grafana_decisions_are_recorded():
    notices = _lire("THIRD_PARTY_NOTICES.md")
    assert "REDIS_7_4_DISTRIBUTION = REJECTED" in notices
    assert "REDIS_REPLACEMENT      = VALKEY" in notices
    assert "GRAFANA_CORE_DEPENDENCY          = FALSE" in notices
    assert "GRAFANA_OPTIONAL_EXTERNAL_SERVICE = TRUE" in notices


def test_implementation_statuses_are_not_claimed_before_the_work_lands():
    """`REDIS_REPLACED_BY_VALKEY` et `GRAFANA_EXTERNALIZED` ne se déclarent pas d'avance."""
    notices = _lire("THIRD_PARTY_NOTICES.md")
    for statut in ("REDIS_REPLACED_BY_VALKEY", "GRAFANA_EXTERNALIZED"):
        assert f"`{statut}`\n> **n'est pas prononcé**" in notices or (
            statut in notices and "n'est pas prononcé" in notices
        ), f"{statut} doit être explicitement non prononcé"
    assert "MANUAL_LICENSE_REVIEW_REQUIRED" in notices
    assert "AGPL_DISTRIBUTION_REVIEW_REQUIRED" in notices


_PREFLIGHT_PRIVE = "docs/governance/PRIVATE_REPOSITORY_PREFLIGHT_2026-08-28.md"


def test_the_private_repository_preflight_measures_rather_than_asserts():
    contenu = _lire(_PREFLIGHT_PRIVE)
    for mesure in (
        "Forks | **0**",
        "Runs déclenchés en août 2026",
        "2 000 minutes",
        "Alertes ouvertes",
    ):
        assert mesure in contenu, f"mesure absente du préflight : {mesure}"


def test_the_preflight_flags_the_three_decisions_needed_before_switching():
    """Quota Actions, CodeQL en privé, checks requis incomplets."""
    contenu = _lire(_PREFLIGHT_PRIVE)
    assert "Quota Actions" in contenu
    assert "CodeQL sur dépôt privé" in contenu
    assert "Checks requis incomplets" in contenu
    assert "PRIVATE_REPOSITORY_PREFLIGHT_READY" in contenu


def test_the_preflight_does_not_claim_the_visibility_changed():
    contenu = _lire(_PREFLIGHT_PRIVE)
    assert "La visibilité n'a pas été modifiée" in contenu
    assert "Visibilité | **publique**" in contenu


def test_the_preflight_says_going_private_does_not_undo_the_past():
    """Un dépôt rendu privé ne récupère pas ce qui a déjà été copié."""
    # Les phrases sont enveloppées, citées et emphasées : on compare le propos.
    brut = _lire(_PREFLIGHT_PRIVE).replace("*", "").replace(">", " ")
    contenu = " ".join(brut.split())
    assert "Le passage en privé protège l'avenir, pas le passé" in contenu
    assert "doit être révoqué" in contenu

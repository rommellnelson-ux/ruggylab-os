"""Tests — la base est épinglée, et les preuves de source sont exigibles.

`3.13-slim` était un tag FLOTTANT : il suit les correctifs et change de contenu
sans prévenir. Une release construite dessus n'est pas reproductible, et les
preuves rassemblées ne décrivent plus l'image livrée. Ces tests empêchent d'y
revenir, et vérifient que rien n'est conclu juridiquement sans validation.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
import yaml

from scripts.debian_source_manifest import (
    _FAMILLES_COPYLEFT,
    _REFERENCE_LICENCE,
    REVUE_JURIDIQUE,
    VERSION_SCRIPT,
    _defauts_qualifies,
    _echecs_de_disponibilite,
    _licence_du_copyright,
    empreintes_du_dsc,
    famille_de_licence,
    paquets_sources,
    provenance,
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
            "copyleft_families": ["GPL"],
            "copyleft_detected": True,
            "source_compliance_review_required": True,
        },
        {
            "binary_package": "attr",
            "copyleft_families": [],
            "copyleft_detected": False,
            "source_compliance_review_required": False,
        },
    ]
    groupes = paquets_sources(binaires, manifeste)
    assert len(groupes) == 1
    groupe = groupes[0]
    assert groupe["produces_binaries"] == ["attr", "libattr1"]
    assert groupe["source_compliance_review_required"] is True, "un binaire copyleft suffit"
    assert groupe["copyleft_families"] == ["GPL"]
    assert groupe["snapshot_package_url"].startswith("https://snapshot.debian.org/package/attr/2")


def test_availability_starts_as_unverified():
    """Tant que l'URL n'a pas été ouverte, elle ne prouve rien."""
    groupes = paquets_sources(
        [{"binary_package": "x", "version": "1", "source_package": "x", "source_version": "1"}],
        [{"binary_package": "x", "copyleft_families": [], "copyleft_detected": False}],
    )
    assert groupes[0]["source_availability"] == "à vérifier"
    assert groupes[0]["source_files_resolution"] == "not_attempted"


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


def test_the_evidence_job_inventories_the_audited_candidate(ci):
    """Le job ne reconstruit plus : il charge l'image que `deploy` publiera.

    Inventorier une image reconstruite produirait des preuves portant sur un
    artefact qui n'est pas celui qu'on livre.
    """
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    noms = [str(e.get("name", "")) for e in etapes]
    assert "Assert the base image is pinned by digest" in noms
    assert any("Load the candidate image" in n for n in noms)
    assert not any("docker build -t" in str(e.get("run", "")) for e in etapes)


def test_the_evidence_job_actually_opens_the_source_urls(ci):
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    generation = next(s for s in etapes if "Generate the Debian source" in str(s.get("name", "")))
    assert "--check-availability" in generation["run"]
    controle = next(s for s in etapes if "reachable" in str(s.get("name", "")))
    assert 'availability"] != "verified"' in controle["run"]


def test_a_network_failure_is_not_downgraded_to_a_warning(ci):
    """Ce job conditionne une publication : une panne bloque, elle n'avertit pas."""
    controle = next(
        s
        for s in ci["jobs"]["debian-source-evidence"]["steps"]
        if "reachable" in str(s.get("name", ""))
    )
    assert "::warning::" not in controle["run"], (
        "un avertissement laisserait passer une preuve non établie"
    )
    assert "sys.exit(1)" in controle["run"]


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


# ── la publication est conditionnée par les preuves ─────────────────────────
#
# Un job qui produit des preuves mais ne bloque rien est un job décoratif.
# Publier l'image sans savoir quels paquets copyleft elle contient ni où leurs
# sources se trouvent, c'est distribuer sans preuve.


def test_the_evidence_job_gates_deployment(ci):
    besoins = ci["jobs"]["deploy"]["needs"]
    assert "debian-source-evidence" in besoins, "deploy peut publier sans les preuves Debian"


def test_release_cannot_bypass_deploy(ci):
    assert "deploy" in ci["jobs"]["release"]["needs"]


def test_no_parallel_publication_path_exists(ci):
    """Toute publication doit passer par `deploy`, donc par les preuves."""
    marqueurs = ("docker/build-push-action", "docker push", "action-gh-release")
    publiants = [
        nom
        for nom, job in ci["jobs"].items()
        if any(
            marqueur in str(etape.get("uses", "")) + str(etape.get("run", ""))
            for etape in (job.get("steps") or [])
            for marqueur in marqueurs
        )
    ]
    assert set(publiants) <= {"deploy", "release"}, f"chemin de publication parallèle : {publiants}"
    for nom in publiants:
        chaine = set(ci["jobs"][nom]["needs"])
        assert "debian-source-evidence" in chaine or "deploy" in chaine, (
            f"{nom} publie sans dépendre des preuves Debian"
        )


def test_the_optional_overlay_never_blocks_publication(ci):
    """Grafana est externe : un cœur sain ne doit pas dépendre de lui."""
    assert "monitoring-overlay" not in ci["jobs"]["deploy"]["needs"]
    assert "monitoring-overlay" not in ci["jobs"]["release"]["needs"]


def test_the_dependency_list_is_explicit_and_extensible(ci):
    """La liste est écrite en clair, prête à accueillir `license-compliance`."""
    besoins = ci["jobs"]["deploy"]["needs"]
    assert isinstance(besoins, list) and len(besoins) >= 8
    for bloquant in (
        "test",
        "test-postgres",
        "codeql",
        "e2e",
        "docker-stack",
        "backup-restore",
        "debian-source-evidence",
        "tag-guard",
    ):
        assert bloquant in besoins, f"gate perdu lors d'une fusion : {bloquant}"


# ── Valkey et le cœur sans Grafana survivent au changement de base ──────────


def test_the_core_still_runs_valkey_without_grafana():
    compose = yaml.safe_load(_lire("docker-compose.yml"))
    assert "valkey" in compose["services"] and "redis" not in compose["services"]
    assert "grafana" not in compose["services"]
    assert "valkey_data" in compose["volumes"] and "redis_data" not in compose["volumes"]
    assert "redis://valkey:6379" in compose["services"]["app"]["environment"]["REDIS_URL"]
    assert "grafana" not in _lire("docker-compose.yml").lower()


def test_the_evidence_job_needs_no_grafana(ci):
    """Le job Debian construit l'image applicative, rien d'autre."""
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    script = " ".join(str(e.get("run", "")) for e in etapes)
    assert "grafana" not in script.lower()
    assert "monitoring.yml" not in script


# ── provenance : un manifeste sans identité ne décrit rien ──────────────────

_CHAMPS_PROVENANCE = (
    "script_version",
    "generated_at",
    "git_sha",
    "image_reference",
    "image_id",
    "base_image_reference",
    "base_image_digest",
    "platform",
    "os",
    "architecture",
)


@pytest.mark.parametrize("champ", _CHAMPS_PROVENANCE)
def test_the_manifest_header_identifies_what_it_describes(champ):
    """Sans provenance, deux manifestes de plateformes différentes se confondent."""
    source = inspect.getsource(provenance)
    assert f'"{champ}"' in source, f"champ de provenance absent : {champ}"


def test_the_script_declares_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION_SCRIPT), VERSION_SCRIPT


def test_the_manifest_warns_that_it_is_single_platform():
    assert "multiplateforme exige un manifeste par plateforme" in inspect.getsource(provenance)


def test_a_multiplatform_deploy_would_need_one_manifest_per_platform(ci):
    """Une publication multiplateforme invaliderait un manifeste unique.

    Les paquets et leurs versions diffèrent d'une architecture à l'autre : un
    manifeste amd64 ne décrirait pas une image arm64. Tant que `deploy` publie
    une seule plateforme, un manifeste suffit ; le jour où `platforms:` apparaît,
    ce test échoue et force à produire un manifeste par plateforme.
    """
    # `deploy` pousse désormais une archive préconstruite : une publication
    # multiplateforme se verrait soit dans un `platforms:` d'action, soit dans
    # un `--platform` de commande.
    script = " ".join(str(e.get("run", "")) for e in ci["jobs"]["deploy"]["steps"])
    actions = [
        (e.get("with") or {}).get("platforms")
        for e in ci["jobs"]["deploy"]["steps"]
        if str(e.get("uses", "")).startswith("docker/build-push-action")
    ]
    plateformes = next((p for p in actions if p), None) or (
        "--platform" if "--platform" in script else None
    )
    if plateformes:
        job = ci["jobs"]["debian-source-evidence"]
        script = " ".join(str(e.get("run", "")) for e in job["steps"])
        assert "strategy" in job or "--platform" in script, (
            f"deploy publie {plateformes} mais un seul manifeste Debian est produit"
        )


# ── fichiers sources exacts ─────────────────────────────────────────────────


def test_the_dsc_checksums_are_read_not_invented():
    dsc = (
        b"Format: 3.0 (quilt)\n"
        b"Checksums-Sha256:\n"
        b" aaaa1111 2111608 tar_1.35+dfsg.orig.tar.xz\n"
        b" bbbb2222 21540 tar_1.35+dfsg-3.1.debian.tar.xz\n"
        b"Files:\n"
        b" cccc3333 2111608 tar_1.35+dfsg.orig.tar.xz\n"
    )
    empreintes = empreintes_du_dsc(dsc)
    assert empreintes["tar_1.35+dfsg.orig.tar.xz"] == ("aaaa1111", 2111608)
    assert empreintes["tar_1.35+dfsg-3.1.debian.tar.xz"] == ("bbbb2222", 21540)
    # Le bloc `Files:` porte des MD5 : les confondre donnerait un faux SHA-256.
    assert "cccc3333" not in [empreinte for empreinte, _ in empreintes.values()]


def test_an_empty_dsc_yields_no_checksum_rather_than_a_guess():
    assert empreintes_du_dsc(b"Format: 3.0 (native)\n") == {}


def test_the_evidence_job_resolves_files_not_just_pages(ci):
    """Un 200 sur la page d'un paquet ne prouve rien sur ses fichiers."""
    etapes = ci["jobs"]["debian-source-evidence"]["steps"]
    generation = next(e for e in etapes if "Generate the Debian source" in str(e.get("name", "")))
    assert "--check-availability" in generation["run"]
    controle = next(e for e in etapes if "reachable" in str(e.get("name", "")))
    assert "source_files" in controle["run"], "le contrôle doit porter sur les FICHIERS"
    assert "sha256" in controle["run"]


# ── neutralité juridique ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "expression,attendu",
    [
        ("GPL-2+", "GPL"),
        ("LGPL-2.1", "LGPL"),
        ("AGPL-3", "AGPL"),
        ("MPL-2.0", "MPL"),
        ("EPL-1.0", "EPL"),
        ("CDDL-1.0", "CDDL"),
        ("MIT", "PERMISSIVE"),
        ("BSD-3-clause", "PERMISSIVE"),
        ("Apache-2.0", "PERMISSIVE"),
    ],
)
def test_licence_families_are_distinguished(expression, attendu):
    """LGPL et AGPL contiennent « GPL » : les confondre fausserait l'analyse."""
    assert famille_de_licence(expression) == attendu


def test_an_unrecognised_licence_is_not_filed_as_reassuring():
    assert famille_de_licence("Licence-Maison-1.0") == "UNKNOWN"
    assert "UNKNOWN" not in _FAMILLES_COPYLEFT


def test_the_script_never_concludes_that_a_written_offer_is_due():
    assert REVUE_JURIDIQUE == "LEGAL_REVIEW_REQUIRED"
    source = (REPO_ROOT / "scripts" / "debian_source_manifest.py").read_text(encoding="utf-8")
    assert "source_offer_obligation" not in source, (
        "l'ancien champ concluait à une obligation : l'automatisation ne le peut pas"
    )
    assert "written_offer_applicability" in source


def test_copyleft_families_are_not_treated_as_interchangeable():
    """La portée de la MPL est le fichier, celle de la GPL l'œuvre."""
    source = (REPO_ROOT / "scripts" / "debian_source_manifest.py").read_text(encoding="utf-8")
    assert "n'imposent pas les mêmes obligations" in source


# ── une panne réseau ne produit pas une preuve verte ────────────────────────


def _groupe(statut="verified", fichiers=None):
    return {
        "source_package": "x",
        "source_version": "1",
        "source_availability": statut,
        "source_files_resolution": "resolved",
        "source_files": fichiers if fichiers is not None else [],
    }


@pytest.mark.parametrize(
    "statut",
    ["unavailable", "timeout", "tls_error", "dns_error", "rate_limited", "unverified"],
)
def test_every_non_verified_status_is_blocking(statut):
    assert _echecs_de_disponibilite([_groupe(statut)]), f"{statut} devrait bloquer"


def test_a_verified_source_with_a_broken_file_still_blocks():
    """Le paquet peut répondre alors qu'un de ses fichiers manque."""
    fichier = {"name": "x.orig.tar.xz", "availability": "timeout", "sha256": "a"}
    assert _echecs_de_disponibilite([_groupe(fichiers=[fichier])])


def test_a_file_without_a_hash_blocks():
    fichier = {"name": "x.tar.xz", "availability": "verified", "sha256": None}
    assert _echecs_de_disponibilite([_groupe(fichiers=[fichier])])


def test_everything_verified_blocks_nothing():
    fichier = {"name": "x.tar.xz", "availability": "verified", "sha256": "abc"}
    assert _echecs_de_disponibilite([_groupe(fichiers=[fichier])]) == []


def test_unresolved_source_files_block():
    groupe = _groupe()
    groupe["source_files_resolution"] = "unresolved"
    assert _echecs_de_disponibilite([groupe])


def test_the_compliance_document_records_the_publication_gate():
    contenu = _lire(CONFORMITE)
    assert "RELEASE_PIPELINE_SOURCE_EVIDENCE_GATED" in contenu
    assert "`monitoring-overlay` n'y figure pas" in contenu


def test_the_compliance_document_explains_the_dgit_case():
    """Le cas debianutils justifie de descendre jusqu'au fichier."""
    contenu = _phrase(CONFORMITE)
    assert "related_archive_files" in contenu
    assert "lui inventer un hash aurait été pire" in contenu


def test_an_incomplete_provenance_fails_rather_than_passes():
    """Un champ vide rendrait le manifeste ininterprétable, sans rien signaler."""
    source = (REPO_ROOT / "scripts" / "debian_source_manifest.py").read_text(encoding="utf-8")
    assert "provenance incomplète, champs vides" in source
    for champ in ("image_id", "platform", "architecture", "base_image_digest", "git_sha"):
        assert f'"{champ}"' in source


def test_each_provenance_field_is_read_separately():
    """Un séparateur qui ne survit pas au passage viderait trois champs d'un coup."""
    source = (REPO_ROOT / "scripts" / "debian_source_manifest.py").read_text(encoding="utf-8")
    assert '_champ("{{.Id}}")' in source
    assert '_champ("{{.Os}}")' in source
    assert '_champ("{{.Architecture}}")' in source

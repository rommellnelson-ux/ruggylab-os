"""Tests — la baseline de qualité G0 (lot C) mesure, et refuse de mal mesurer.

Le lot A décrit une architecture : ses artefacts se comparent au code, et un
écart est une erreur. Le lot C **mesure** : deux exécutions de la même suite sur
la même révision ne donnent pas les mêmes latences, et re-mesurer ne pourrait
donc jamais démontrer qu'un chiffre publié est périmé. Ce que ces tests
vérifient n'est pas la valeur mesurée — ils ne connaissent aucun seuil et ne
doivent jamais en connaître — mais la **capacité des contrôles à refuser une
mesure dont on ne pourrait rien conclure**.

Chaque test de refus a été rejoué contre le contrôle *avant* qu'il existe :
sans le contrôle, la mutation passait. C'est la seule manière de savoir qu'un
test n'est pas décoratif. Les tests marqués « témoin » vérifient l'inverse — que
la mesure intacte est bien acceptée — sans quoi un contrôle qui refuserait tout
paraîtrait excellent.

Les charges utiles sont **construites ici**, jamais lues dans un artefact
versionné. Muter un générateur sans régénérer son fichier ne prouverait rien :
le test lirait l'ancien fichier et passerait, alors que le générateur est cassé.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs" / "g0"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"
SURCHARGE = REPO_ROOT / "scripts" / "g0_perf_overlay.yml"

#: Verdicts que le lot C ne prononce jamais. Constater n'est pas décider.
VERDICTS_INTERDITS = (
    "G0_PASS",
    "REAL_DATA_GO",
    "SITE_PRODUCTION_GO",
    "DISTRIBUTION_GO",
)


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _aplati(chemin: Path) -> str:
    """Le texte d'un document, débarrassé de sa mise en forme Markdown.

    Une phrase coupée par un retour à la ligne ne doit pas faire échouer un test
    qui la cherche : ce serait faire dépendre une preuve de la largeur de ses
    lignes.
    """
    lignes = [re.sub(r"^\s*>\s?", "", ligne) for ligne in _lire(chemin).splitlines()]
    return " ".join(" ".join(lignes).replace("*", "").replace("`", "").split())


# ── Ensembles d'entrée et pièges de plateforme ──────────────────────────────


def test_les_deux_ensembles_dentree_du_lot_c_existent():
    """Sans ensemble d'entrée déclaré, une provenance ne désigne rien."""
    from scripts.g0_provenance import ENSEMBLES_ENTREE

    assert "coverage" in ENSEMBLES_ENTREE
    assert "performance" in ENSEMBLES_ENTREE


def test_la_surcharge_de_mesure_reste_hors_de_lensemble_inventory():
    """L'appareil de mesure ne doit pas déplacer l'empreinte du lot A.

    `deploy/**` appartient à l'ensemble `inventory` d'une baseline déjà
    fusionnée. Y déposer cette surcharge aurait obligé à régénérer l'inventaire
    d'architecture pour un réglage qui ne décrit aucun déploiement — et un
    inventaire régénéré pour une raison étrangère est un inventaire qu'on relit
    moins.
    """
    from scripts.g0_provenance import fichiers_entree

    assert SURCHARGE.is_file(), "la surcharge de mesure a disparu"
    assert not (REPO_ROOT / "deploy" / "g0-perf-overlay.yml").exists()
    assert SURCHARGE not in fichiers_entree("inventory")
    assert SURCHARGE in fichiers_entree("performance")


def test_modifier_la_surcharge_change_lempreinte_de_performance():
    """Mutation — une surcharge modifiée doit changer l'empreinte.

    Ce contrôle vaut mieux qu'un test de présence : il prouve que le fichier est
    réellement lu. La surcharge désactive les limiteurs de débit ; si la
    modifier ne changeait rien, on pourrait publier une baseline mesurée dans un
    autre régime sans que la provenance en garde trace.
    """
    from scripts.g0_provenance import empreinte_entrees

    avant, _ = empreinte_entrees("performance")
    original = SURCHARGE.read_bytes()
    try:
        SURCHARGE.write_bytes(original + b"\n# mutation temporaire\n")
        apres, _ = empreinte_entrees("performance")
    finally:
        SURCHARGE.write_bytes(original)
    assert apres != avant, "l'empreinte ignore la surcharge : elle ne la lit pas"
    assert SURCHARGE.read_bytes() == original, "la mutation n'a pas ete annulee"


@pytest.mark.parametrize("ensemble", ["coverage", "performance"])
def test_le_tri_des_entrees_porte_sur_la_chaine_posix(ensemble: str):
    """Le défaut précis qui a fait échouer le lot A.

    Comparer deux `Path` emploie la casse repliée sous Windows et la casse
    exacte sous Linux. Comme l'ordre entre dans l'empreinte, la même
    arborescence produisait deux valeurs selon la machine.
    """
    from scripts.g0_provenance import chemin_relatif, fichiers_entree

    fichiers = fichiers_entree(ensemble)
    assert fichiers == sorted(fichiers, key=chemin_relatif)
    melange = ["app/Z.py", "app/a.py", "app/B.py"]
    assert sorted(melange) == ["app/B.py", "app/Z.py", "app/a.py"]


# ── Couverture : construction d'un rapport de référence ─────────────────────


def _rapport_json(
    modules: list[str] | None = None,
    *,
    branches: bool = True,
    jamais_execute: int = 0,
) -> dict[str, Any]:
    """Un rapport `coverage json` synthétique, complet et cohérent.

    Complet au sens du contrôle de périmètre : il mentionne **tous** les modules
    de `app/`. Un rapport partiel serait refusé, ce qui est précisément l'un des
    comportements testés plus bas.
    """
    from scripts.g0_coverage_summary import fichiers_application

    chemins = fichiers_application() if modules is None else modules
    fichiers: dict[str, Any] = {}
    for indice, chemin in enumerate(chemins):
        instructions = 10 + (indice % 7)
        couvertes = 0 if indice < jamais_execute else max(1, instructions - (indice % 4))
        total_branches = 4 if branches else 0
        branches_couvertes = 0 if not branches else max(1, total_branches - (indice % 3))
        fichiers[chemin] = {
            "summary": {
                "num_statements": instructions,
                "covered_lines": couvertes,
                "missing_lines": instructions - couvertes,
                "num_branches": total_branches,
                "covered_branches": branches_couvertes,
                "num_partial_branches": 0,
                "excluded_lines": 0,
            }
        }
    resumes = [f["summary"] for f in fichiers.values()]
    totaux = {
        "num_statements": sum(r["num_statements"] for r in resumes),
        "covered_lines": sum(r["covered_lines"] for r in resumes),
        "missing_lines": sum(r["missing_lines"] for r in resumes),
        "num_branches": sum(r["num_branches"] for r in resumes),
        "covered_branches": sum(r["covered_branches"] for r in resumes),
        "num_partial_branches": 0,
        "missing_branches": sum(r["num_branches"] - r["covered_branches"] for r in resumes),
        "excluded_lines": 0,
    }
    return {
        "meta": {
            "version": "7.16.0",
            "branch_coverage": branches,
            "timestamp": "2026-09-09T00:00:00",
        },
        "files": fichiers,
        "totals": totaux,
    }


def _rapport_xml(rapport_json: dict[str, Any], *, conditions: int = 1) -> dict[str, Any]:
    """Le pendant XML du rapport JSON, tel que `lire_xml` le renverrait."""
    totaux = rapport_json["totals"]
    return {
        "line_rate": 0.5,
        "branch_rate": 0.5,
        "lines_covered": totaux["covered_lines"],
        "lines_valid": totaux["num_statements"],
        "branches_covered": totaux["covered_branches"],
        "branches_valid": totaux["num_branches"],
        "condition_coverage_attributs": conditions,
        "packages": ["app", "app.api", "app.services"],
        "files": sorted(rapport_json["files"]),
    }


@pytest.fixture
def resume_couverture() -> dict[str, Any]:
    rapport = _rapport_json()
    from scripts.g0_coverage_summary import construire

    return construire(rapport, _rapport_xml(rapport))


# ── Couverture : témoin, puis mutations ─────────────────────────────────────


def test_temoin_un_rapport_complet_est_accepte(resume_couverture):
    """Témoin. Un contrôle qui refuserait tout paraîtrait excellent."""
    from scripts.g0_coverage_summary import controler

    assert controler(resume_couverture) == []


def test_mutation_cov_branch_disparu_est_refusee():
    """Mutation 1 — `--cov-branch` retiré de la commande.

    Un rapport lignes seules est indiscernable, sur les pourcentages, d'un
    rapport de branches. Seuls `meta.branch_coverage` et les attributs
    `condition-coverage` du XML le disent.
    """
    from scripts.g0_coverage_summary import construire, controler

    rapport = _rapport_json(branches=False)
    resume = construire(rapport, _rapport_xml(rapport, conditions=0))
    ecarts = controler(resume)
    assert any("branches non mesurees" in e for e in ecarts), ecarts


def test_mutation_xml_sans_attribut_condition_coverage_est_refusee(resume_couverture):
    """Mutation 2 — un XML sans `condition-coverage` ne prouve aucune branche."""
    from scripts.g0_coverage_summary import controler

    mute = copy.deepcopy(resume_couverture)
    mute["payload"]["xml_cross_check"]["condition_coverage_attributs"] = 0
    assert any("condition-coverage" in e for e in controler(mute))


def test_mutation_xml_incomplet_est_refusee(resume_couverture):
    """Mutation 3 — totaux XML absents : le rapport ne se croise plus."""
    from scripts.g0_coverage_summary import controler

    mute = copy.deepcopy(resume_couverture)
    mute["payload"]["xml_cross_check"]["lines_valid"] = None
    mute["payload"]["xml_cross_check"]["packages"] = []
    ecarts = controler(mute)
    assert any("XML incomplet" in e for e in ecarts), ecarts


def test_mutation_paquet_critique_omis_est_refusee(resume_couverture):
    """Mutation 4 — un regroupement retiré du résumé.

    Omettre `app/services/csa_sync` laisserait croire que l'intégration CSA a
    été mesurée alors qu'elle n'apparaîtrait nulle part.
    """
    from scripts.g0_coverage_summary import controler

    mute = copy.deepcopy(resume_couverture)
    del mute["payload"]["by_package"]["app/services/csa_sync"]
    assert any("csa_sync" in e for e in controler(mute))


def test_mutation_fichier_retire_du_perimetre_est_refusee(resume_couverture):
    """Mutation 5 — un module de `app/` absent du rapport.

    C'est la forme la plus flatteuse de tricherie : `--cov=app.api` produit un
    rapport parfaitement valide dont le pourcentage ignore tout le reste.
    """
    from scripts.g0_coverage_summary import controler

    mute = copy.deepcopy(resume_couverture)
    retire = mute["payload"]["by_module"].pop()
    ecarts = controler(mute)
    assert any("perimetre reduit" in e for e in ecarts), (retire, ecarts)


def test_mutation_resultat_sans_donnees_de_branches_est_refusee():
    """Mutation 6 — branches déclarées mesurées, mais aucune branche dans le XML."""
    from scripts.g0_coverage_summary import construire, controler

    rapport = _rapport_json(branches=False)
    rapport["meta"]["branch_coverage"] = True  # le drapeau ment
    resume = construire(rapport, _rapport_xml(rapport, conditions=0))
    ecarts = controler(resume)
    assert any("condition-coverage" in e for e in ecarts), ecarts


def test_mutation_incoherence_entre_xml_et_json_est_refusee(resume_couverture):
    """Mutation 7 — les deux sources divergent : l'une des deux est fausse."""
    from scripts.g0_coverage_summary import controler

    mute = copy.deepcopy(resume_couverture)
    mute["payload"]["xml_cross_check"]["lines_covered"] += 1000
    assert any("incoherence XML/JSON" in e for e in controler(mute))


def test_un_xml_tronque_nest_pas_lu_comme_un_rapport(tmp_path: Path):
    """Un fichier coupé en deux ne doit pas produire un résumé partiel silencieux."""
    import xml.etree.ElementTree as ET

    from scripts.g0_coverage_summary import lire_xml

    tronque = tmp_path / "coverage.xml"
    tronque.write_text('<?xml version="1.0" ?>\n<coverage lines-valid="10">\n  <pack', "utf-8")
    with pytest.raises(ET.ParseError):
        lire_xml(tronque)


def test_une_racine_xml_etrangere_est_refusee(tmp_path: Path):
    from scripts.g0_coverage_summary import lire_xml

    autre = tmp_path / "coverage.xml"
    autre.write_text("<testsuite name='x'></testsuite>", encoding="utf-8")
    with pytest.raises(ValueError, match="attendu <coverage>"):
        lire_xml(autre)


def test_zero_instruction_nest_jamais_cent_pour_cent():
    """Un module vide couvert à 100 % gonflerait la moyenne sans rien prouver."""
    from scripts.g0_coverage_summary import _pourcentage

    assert _pourcentage(0, 0) == 0.0
    assert _pourcentage(1, 2) == 50.0


def test_les_regroupements_exiges_sont_tous_declares():
    from scripts.g0_coverage_summary import REGROUPEMENTS

    for prefixe in (
        "app/api",
        "app/core",
        "app/services",
        "app/services/validation",
        "app/services/interfacing",
        "app/services/csa_sync",
        "app/models",
        "app/utils",
    ):
        assert prefixe in REGROUPEMENTS


def test_aucun_seuil_de_couverture_nulle_part():
    """G0 constate. Un seuil se contourne en choisissant les tests.

    Le contrôle porte sur le générateur **et** sur le workflow : c'est là qu'un
    `--cov-fail-under` s'ajouterait le plus naturellement.
    """
    source = _lire(REPO_ROOT / "scripts" / "g0_coverage_summary.py")
    assert "fail_under" not in source
    assert "fail-under" not in source
    if WORKFLOW.is_file():
        workflow = _lire(WORKFLOW)
        assert "--cov-fail-under" not in workflow
        assert "fail_under" not in workflow


# ── Performance : construction d'une mesure de référence ────────────────────


def _mesure_valide() -> dict[str, Any]:
    """Une mesure complète et cohérente, la plus petite possible.

    Elle sert de témoin et de base à chaque mutation. La construire ici plutôt
    que de relire un fichier produit par une exécution évite le faux négatif le
    plus courant : un test qui passerait parce qu'il lit un artefact périmé.
    """
    from scripts.g0_perf_baseline import (
        MARQUE_SYNTHETIQUE,
        NOMS_SYNTHETIQUES,
        PRENOMS_SYNTHETIQUES,
        SCENARIOS,
        empreinte_scenario,
    )

    noms = list(SCENARIOS)
    latences = {"min": 1.0, "mean": 2.0, "p50": 2.0, "p95": 3.0, "p99": 4.0, "max": 5.0}
    scenarios = {
        s.nom: {
            "samples": 12,
            "successes": 12,
            "errors": 0,
            "error_rate": 0.0,
            "errors_by_type": {},
            "latency_ms": dict(latences),
            "throughput_rps": 4.0,
            "completed": True,
        }
        for s in noms
    }
    agregat = {
        "samples": 12 * len(noms),
        "successes": 12 * len(noms),
        "errors": 0,
        "error_rate": 0.0,
        "errors_by_type": {},
        "latency_ms": dict(latences),
        "throughput_rps": 40.0,
        "completed": True,
    }
    return {
        "run": {
            "run_id": "abcdef0123",
            "seed": 20260909,
            "started_at": "2026-09-09T00:00:00Z",
            "duration_seconds": 120.0,
            "concurrency_levels": [1, 3],
            "repetitions": 3,
            "iterations_per_worker": 5,
            "warmup_iterations_per_worker": 2,
            "scenario_order": [s.nom for s in noms],
            "scenario_sha256": empreinte_scenario(),
            "percentile_method": "nearest-rank (ceil(p/100*n)) sans interpolation",
            "clock_source": "time.perf_counter (monotone)",
            "clock_monotonic": True,
            "retries": 0,
            "command": "python scripts/g0_perf_baseline.py --run",
            "base_url_scheme": "https",
        },
        "dataset": {
            "synthetic_marker": MARQUE_SYNTHETIQUE,
            "identifier_prefix": f"{MARQUE_SYNTHETIQUE}-abcdef0123",
            "name_vocabulary": sorted(PRENOMS_SYNTHETIQUES + NOMS_SYNTHETIQUES),
            "names_used": ["Alpha", "Temoin"],
            "identifiers_created": 42,
            "sample_identifiers": [f"{MARQUE_SYNTHETIQUE}-abcdef0123-L1-R0-W0-0000"],
            "all_identifiers_prefixed": True,
            "source": "genere par scripts/g0_perf_baseline.py",
        },
        "application_health": {"before": True, "after": True},
        "levels": {
            "1": {
                "concurrency": 1,
                "repetitions": [{"index": i} for i in range(3)],
                "wall_clock_seconds": 60.0,
                "scenarios": copy.deepcopy(scenarios),
                "aggregate": copy.deepcopy(agregat),
                "resources": {},
            },
            "3": {
                "concurrency": 3,
                "repetitions": [{"index": i} for i in range(3)],
                "wall_clock_seconds": 60.0,
                "scenarios": copy.deepcopy(scenarios),
                "aggregate": copy.deepcopy(agregat),
                "resources": {},
            },
        },
        "errors_by_type_total": {},
        "environment": {
            "git_commit": "0" * 40,
            "runner": "ubuntu-latest",
            "os": "Linux 6.8",
            "architecture": "x86_64",
            "cpu_count": 4,
            "memory_total_bytes": 16_000_000_000,
            "python_version": "3.13.0",
            "docker_version": "27.0.0",
            "image_id": "sha256:" + "a" * 64,
            "postgres_version": "PostgreSQL 16.6",
            "valkey_version": "7.2.4",
            "application_configuration": {"RATE_LIMIT_ENABLED": "false"},
            "effective_external_switches": {
                "available": True,
                "settings": {
                    "CSA_SYNC_ENABLED": False,
                    "ENABLE_DH36_LISTENER": False,
                    "ANALYZER_RAW_LISTENER_ENABLED": False,
                },
            },
            "external_network_calls": False,
        },
        "validity_policy": {"min_samples_per_scenario_per_level": 10},
    }


@pytest.fixture
def mesure() -> dict[str, Any]:
    return _mesure_valide()


# ── Performance : témoin, puis mutations ────────────────────────────────────


def test_temoin_une_mesure_complete_est_acceptee(mesure):
    """Témoin. Sans lui, un contrôle qui refuse tout passerait pour rigoureux."""
    from scripts.g0_perf_baseline import valider

    assert valider(mesure) == []


def test_mutation_p99_absent_est_refusee(mesure):
    """Mutation 8 — un p99 manquant : la queue de distribution disparaît."""
    from scripts.g0_perf_baseline import valider

    mesure["levels"]["3"]["scenarios"]["auth"]["latency_ms"]["p99"] = None
    assert any("sans p99" in m for m in valider(mesure))


def test_mutation_agregat_sans_p99_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    mesure["levels"]["1"]["aggregate"]["latency_ms"]["p99"] = None
    assert any("agregat sans p99" in m for m in valider(mesure))


def test_mutation_echantillons_insuffisants_est_refusee(mesure):
    """Mutation 9 — trop peu de mesures : un centile sur trois valeurs ne dit rien."""
    from scripts.g0_perf_baseline import valider

    mesure["levels"]["1"]["scenarios"]["worklist"]["samples"] = 3
    assert any("sous-echantillonne" in m for m in valider(mesure))


def test_mutation_moins_de_trois_repetitions_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    mesure["run"]["repetitions"] = 2
    for niveau in mesure["levels"].values():
        niveau["repetitions"] = [{"index": 0}, {"index": 1}]
    assert any("moins de trois repetitions" in m for m in valider(mesure))


def test_mutation_erreur_applicative_masquee_est_refusee(mesure):
    """Mutation 10 — une erreur effacée de l'agrégat.

    C'est le défaut que le lot D ne verrait plus : un taux d'erreur ramené à
    zéro après coup, ou par un réessai. La somme des scénarios contredit
    l'agrégat, et c'est ce désaccord qui est détecté.
    """
    from scripts.g0_perf_baseline import valider

    mesure["levels"]["3"]["scenarios"]["invoice_create"]["errors"] = 2
    mesure["levels"]["3"]["scenarios"]["invoice_create"]["errors_by_type"] = {"http_500": 2}
    motifs = valider(mesure)
    assert any("erreur a ete masquee" in m for m in motifs), motifs


def test_mutation_classification_des_erreurs_incomplete_est_refusee(mesure):
    """Une erreur comptée mais non classée sortirait du champ du lot D."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["scenarios"]["invoice_create"]["errors"] = 1
        niveau["scenarios"]["invoice_create"]["errors_by_type"] = {"http_500": 1}
        niveau["aggregate"]["errors"] = 1
    mesure["errors_by_type_total"] = {}
    assert any("classification est incomplete" in m for m in valider(mesure))


def test_mutation_reessais_declares_est_refusee(mesure):
    """Un réessai transformerait 8 % d'erreurs en 0 % apparent."""
    from scripts.g0_perf_baseline import valider

    mesure["run"]["retries"] = 3
    assert any("reessais" in m for m in valider(mesure))


def test_mutation_donnees_non_synthetiques_est_refusee(mesure):
    """Mutation 11 — un identifiant sans marque : la mesure a peut-être touché du réel."""
    from scripts.g0_perf_baseline import valider

    mesure["dataset"]["sample_identifiers"] = ["PATIENT-2026-000123"]
    mesure["dataset"]["all_identifiers_prefixed"] = False
    motifs = valider(mesure)
    assert any("non synthetique" in m for m in motifs)
    assert any("marque synthetique" in m for m in motifs)


def test_mutation_nom_hors_vocabulaire_est_refusee(mesure):
    """Un nom réel dans un jeu dit synthétique doit arrêter la publication."""
    from scripts.g0_perf_baseline import valider

    mesure["dataset"]["names_used"] = ["Alpha", "Dupont"]
    assert any("hors vocabulaire" in m for m in valider(mesure))


def test_mutation_environnement_incomplet_est_refusee(mesure):
    """Mutation 12 — une baseline sans machine ne se compare à rien."""
    from scripts.g0_perf_baseline import valider

    mesure["environment"]["docker_version"] = None
    assert any("environnement non decrit : docker_version" in m for m in valider(mesure))


def test_mutation_systeme_externe_actif_est_refusee(mesure):
    """Mutation 13 — CSA activé : ce n'est plus le laboratoire qu'on mesure."""
    from scripts.g0_perf_baseline import valider

    mesure["environment"]["effective_external_switches"]["settings"]["CSA_SYNC_ENABLED"] = True
    assert any("systeme externe actif" in m for m in valider(mesure))


def test_mutation_reglages_effectifs_non_lus_est_refusee(mesure):
    """Une variable d'environnement absente ne vaut pas une preuve de désactivation."""
    from scripts.g0_perf_baseline import valider

    mesure["environment"]["effective_external_switches"] = {"available": False}
    assert any("reglages effectifs non lus" in m for m in valider(mesure))


def test_mutation_scenario_non_termine_est_refusee(mesure):
    """Mutation 14 — un scénario qui n'aboutit jamais n'a pas été mesuré."""
    from scripts.g0_perf_baseline import valider

    mesure["levels"]["1"]["scenarios"]["result_release"]["completed"] = False
    assert any("non termine" in m for m in valider(mesure))


def test_mutation_scenario_absent_du_resultat_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    del mesure["levels"]["3"]["scenarios"]["payment_create"]
    assert any("payment_create` absent" in m for m in valider(mesure))


def test_mutation_application_non_saine_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    mesure["application_health"]["after"] = False
    assert any("non saine apres" in m for m in valider(mesure))


def test_mutation_horloge_non_monotone_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    mesure["run"]["clock_monotonic"] = False
    assert any("horloge non monotone" in m for m in valider(mesure))


def test_mutation_niveau_de_concurrence_non_mesure_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    del mesure["levels"]["3"]
    assert any("niveaux de concurrence non mesures" in m for m in valider(mesure))


# ── Provenance de la mesure ─────────────────────────────────────────────────


def _provenance_valide(mesure: dict[str, Any]) -> dict[str, Any]:
    from scripts.g0_perf_baseline import construire_provenance

    return construire_provenance(mesure, mesure["run"]["command"])


def test_temoin_une_provenance_complete_est_acceptee(mesure):
    from scripts.g0_perf_baseline import valider_provenance

    assert valider_provenance(_provenance_valide(mesure), mesure) == []


def test_mutation_provenance_absente_est_refusee(mesure):
    """Mutation 15 — pas de provenance : des chiffres sans origine."""
    from scripts.g0_perf_baseline import valider_provenance

    assert valider_provenance({}, mesure) != []
    assert valider_provenance({"volatile": {}}, mesure) != []


def test_mutation_provenance_incomplete_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider_provenance

    entete = _provenance_valide(mesure)
    del entete["deterministic"]["relevant_input_tree_sha256"]
    assert any("relevant_input_tree_sha256" in m for m in valider_provenance(entete, mesure))


def test_mutation_scenario_modifie_sans_changement_dempreinte_est_refusee(mesure):
    """Mutation 16 — le parcours change, l'empreinte reste.

    Sans ce contrôle, on pourrait retirer l'écriture du scénario et republier
    une provenance décrivant l'ancien parcours : la baseline dirait mesurer un
    laboratoire alors qu'elle ne mesurerait plus que des lectures.
    """
    from scripts.g0_perf_baseline import valider_provenance

    entete = _provenance_valide(mesure)
    entete["deterministic"]["scenario_sha256"] = "0" * 64
    motifs = valider_provenance(entete, mesure)
    assert any("empreinte du scenario" in m for m in motifs), motifs


def test_lempreinte_du_scenario_depend_reellement_du_parcours(monkeypatch):
    """Le contrôle précédent ne vaut que si l'empreinte bouge quand le parcours bouge."""
    import scripts.g0_perf_baseline as banc

    avant = banc.empreinte_scenario()
    modifies = list(banc.SCENARIOS)
    remplace = modifies[1]
    modifies[1] = banc.Scenario(
        remplace.nom, remplace.genre, remplace.methode, "/api/v1/autre", remplace.description
    )
    monkeypatch.setattr(banc, "SCENARIOS", tuple(modifies))
    assert banc.empreinte_scenario() != avant
    monkeypatch.undo()
    assert banc.empreinte_scenario() == avant


def test_une_reference_temporaire_ne_peut_pas_servir_de_source(mesure):
    """`tmp/g0-quality-work` disparaîtra : une provenance qui la cite ne se rejoue pas."""
    from scripts.g0_perf_baseline import valider_provenance

    entete = _provenance_valide(mesure)
    entete["deterministic"]["baseline_input_ref"] = "tmp/g0-quality-work"
    assert any("reference temporaire" in m for m in valider_provenance(entete, mesure))


def test_provenance_incoherente_avec_la_mesure_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider_provenance

    entete = _provenance_valide(mesure)
    entete["deterministic"]["concurrency_levels"] = [1]
    assert any("provenance incoherente" in m for m in valider_provenance(entete, mesure))


# ── Méthode de mesure ───────────────────────────────────────────────────────


def test_les_centiles_renvoient_une_valeur_reellement_observee():
    """Rang le plus proche, sans interpolation.

    Sur des effectifs modestes, l'interpolation fabrique des valeurs que
    personne n'a mesurées — et l'on publierait alors un p99 qui n'a jamais eu
    lieu.
    """
    from scripts.g0_perf_baseline import _centile

    serie = [10.0, 20.0, 30.0, 40.0, 100.0]
    assert _centile(serie, 50) == 30.0
    assert _centile(serie, 99) == 100.0
    assert _centile(serie, 1) == 10.0
    assert _centile([], 95) == 0.0
    for valeur in (_centile(serie, 95), _centile(serie, 50)):
        assert valeur in serie


def test_les_niveaux_de_concurrence_par_defaut_couvrent_le_premier_usage():
    """1, 3, 5, 10 — 3 est le premier usage envisagé au CSA GR Plateau."""
    from scripts.g0_perf_baseline import NIVEAUX_PAR_DEFAUT

    assert NIVEAUX_PAR_DEFAUT == (1, 3, 5, 10)


def test_le_banc_ne_reessaie_jamais_une_requete():
    """Un réessai masquerait précisément ce que le lot D doit voir."""
    source = _lire(REPO_ROOT / "scripts" / "g0_perf_baseline.py")
    assert "transport=httpx.HTTPTransport(retries" not in source
    assert "retries=" not in source
    assert '"retries": 0' in source


def test_aucun_objectif_de_latence_dans_le_banc():
    """Une latence élevée est un résultat. Aucun seuil ne doit exister ici."""
    source = _lire(REPO_ROOT / "scripts" / "g0_perf_baseline.py")
    for interdit in ("MAX_LATENCY", "SLA_", "latency_budget", "objectif_latence"):
        assert interdit not in source
    # Le seul seuil du script porte sur la JOURNALISATION des requêtes lentes :
    # il décide de ce qu'on observe, jamais de ce qu'on accepte.
    assert "slow_query_threshold_ms" in source


def test_le_scenario_couvre_lectures_et_ecritures_du_parcours_clinique():
    """Un banc qui ne ferait que lire décrirait un laboratoire qui n'existe pas."""
    from scripts.g0_perf_baseline import SCENARIOS

    par_nom = {s.nom: s for s in SCENARIOS}
    for lecture in (
        "auth",
        "patient_search",
        "worklist",
        "order_read",
        "result_read",
        "dashboard",
    ):
        assert par_nom[lecture].genre == "read"
    for ecriture in (
        "patient_create",
        "order_create",
        "sample_create",
        "result_create",
        "result_release",
        "invoice_create",
        "payment_create",
    ):
        assert par_nom[ecriture].genre == "write"


# ── Documents ───────────────────────────────────────────────────────────────

BANDEAU = (
    "INTERNAL — SECURITY ARCHITECTURE",
    "BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT",
    "Ce bandeau est une mention de classification, pas un contrôle d'accès",
)


@pytest.mark.parametrize("document", ["COVERAGE.md", "PERFORMANCE.md"])
def test_le_bandeau_de_classification_est_repris_a_lidentique(document: str):
    texte = _aplati(DOCS / document)
    for phrase in BANDEAU:
        assert phrase in texte, f"{document} : bandeau incomplet ({phrase!r})"


@pytest.mark.parametrize("document", ["COVERAGE.md", "PERFORMANCE.md"])
def test_aucun_verdict_de_gouvernance_dans_les_documents(document: str):
    texte = _lire(DOCS / document)
    for verdict in VERDICTS_INTERDITS:
        assert verdict not in texte, f"{document} prononce {verdict}"


def test_la_couverture_nest_jamais_declaree_suffisante():
    """Une baseline constate. « Suffisante » serait un jugement sans référentiel."""
    texte = _aplati(DOCS / "COVERAGE.md").lower()
    for formule in (
        "couverture suffisante",
        "couverture est suffisante",
        "couverture satisfaisante",
        "couverture acceptable",
        "bonne couverture",
    ):
        assert formule not in texte, f"COVERAGE.md affirme « {formule} »"


def test_coverage_md_documente_la_commande_et_le_perimetre():
    texte = _aplati(DOCS / "COVERAGE.md")
    assert "--cov-branch" in texte
    assert "--cov=app" in texte
    for mention in (
        "Playwright",
        "jamais importé",
        "exclusion",
    ):
        assert mention.lower() in texte.lower(), f"COVERAGE.md ne traite pas : {mention}"


def test_coverage_md_distingue_ce_qui_est_instrumente_de_ce_qui_ne_lest_pas():
    """Prétendre couvert un parcours non instrumenté serait la pire erreur possible."""
    texte = _aplati(DOCS / "COVERAGE.md").lower()
    assert "non instrumenté" in texte
    assert "instrumenté" in texte


def test_performance_md_decrit_les_niveaux_et_les_limiteurs():
    texte = _aplati(DOCS / "PERFORMANCE.md")
    for niveau in ("1", "3", "5", "10"):
        assert niveau in texte
    aplati = texte.lower()
    assert "rate_limit_enabled" in aplati or "limiteur" in aplati
    assert "synthétique" in aplati


def test_performance_md_ne_presente_aucune_latence_comme_un_echec():
    texte = _aplati(DOCS / "PERFORMANCE.md").lower()
    assert "latence élevée est un résultat" in texte or "latence élevée est une mesure" in texte


# ── Workflow ────────────────────────────────────────────────────────────────


def test_le_workflow_du_lot_c_existe_et_ne_touche_pas_a_ci_yml():
    """Le lot B possède `ci.yml`. Un conflit de fusion sur ce fichier serait évitable."""
    assert WORKFLOW.is_file(), "le workflow du lot C est absent"
    contenu = _lire(WORKFLOW)
    assert "G0 — Coverage baseline" in contenu
    assert "G0 — Performance baseline" in contenu


def test_le_workflow_ne_publie_ni_image_ni_tag_ni_statut():
    """Une mesure ne doit rien pouvoir publier ni décider."""
    contenu = _lire(WORKFLOW)
    for interdit in (
        "docker push",
        "ghcr.io",
        "git tag",
        "gh release",
        "packages: write",
        "contents: write",
    ):
        assert interdit not in contenu, f"le workflow du lot C contient `{interdit}`"


def test_le_workflow_valide_la_provenance_de_la_mesure():
    contenu = _lire(WORKFLOW)
    assert "--provenance" in contenu
    assert "--validate" in contenu


def test_le_workflow_verifie_les_statuts_de_gouvernance():
    contenu = _lire(WORKFLOW)
    assert "REAL_DATA_NO_GO" in contenu
    assert "DISTRIBUTION_NO_GO" in contenu


# ── Invariants ──────────────────────────────────────────────────────────────


def test_les_statuts_de_gouvernance_sont_inchanges():
    clinique = _lire(REPO_ROOT / "docs" / "governance" / "CLINICAL_STATUS").strip()
    distribution = _lire(REPO_ROOT / "docs" / "governance" / "DISTRIBUTION_STATUS").strip()
    assert clinique == "REAL_DATA_NO_GO"
    assert distribution == "DISTRIBUTION_NO_GO"


def test_les_interrupteurs_externes_restent_desactives_par_defaut():
    """Le lot C ne doit activer ni CSA ni aucun automate, même pour mesurer."""
    from app.core.config import Settings

    champs = Settings.model_fields
    for nom in ("CSA_SYNC_ENABLED", "ENABLE_DH36_LISTENER", "ANALYZER_RAW_LISTENER_ENABLED"):
        assert champs[nom].default is False, f"{nom} n'est plus desactive par defaut"


def test_la_surcharge_de_mesure_ne_touche_quaux_limiteurs_de_debit():
    """Elle désactive deux limiteurs, et rien d'autre — surtout pas CSA.

    Une surcharge qui aurait dérivé jusqu'à activer un flux sortant ferait
    mesurer autre chose que le laboratoire, sans que la baseline le dise.
    """
    import yaml

    contenu = yaml.safe_load(_lire(SURCHARGE))
    services = contenu["services"]
    assert set(services) == {"app"}
    assert services["app"]["environment"] == {
        "RATE_LIMIT_ENABLED": "false",
        "LOGIN_RATE_LIMIT_ENABLED": "false",
    }


def test_les_mesures_ne_sont_pas_versionnees():
    """Une mesure versionnée serait une preuve que rien ne peut contredire.

    Re-mesurer ne redonne jamais les mêmes latences : aucun contrôle ne pourrait
    détecter qu'un fichier versionné est périmé. Les cinq fichiers sont produits
    à chaque exécution du workflow et publiés comme artefacts de CI.
    """
    ignore = _lire(REPO_ROOT / ".gitignore")
    for nom in (
        "artifacts/g0/coverage.xml",
        "artifacts/g0/coverage.json",
        "artifacts/g0/coverage-summary.json",
        "artifacts/g0/perf-baseline.json",
        "artifacts/g0/perf-provenance.json",
    ):
        assert nom in ignore, f"{nom} n'est pas exclu du suivi de version"


def test_le_resume_de_couverture_est_serialisable(resume_couverture):
    """Un résumé qui ne s'écrit pas ne se relit pas dans une revue."""
    texte = json.dumps(resume_couverture, ensure_ascii=False, sort_keys=True)
    assert json.loads(texte)["payload"]["totals"]["statements"] > 0

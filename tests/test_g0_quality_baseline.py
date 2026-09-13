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


def test_la_surcharge_de_mesure_nest_jamais_prise_pour_un_deploiement():
    """L'appareil de mesure ne doit jamais passer pour une configuration livrée.

    Version précédente de ce test : la surcharge devait rester HORS de
    l'ensemble `inventory`. Elle y entre désormais, parce que l'ensemble
    couvre `scripts/**/*.yml` depuis que les scripts d'exploitation sont sous
    empreinte. L'assertion a donc été revue plutôt que contournée.

    Ce que cela change, exactement : modifier la surcharge oblige maintenant à
    régénérer `inventory.json`, dont la charge utile ne bougera pourtant pas.
    C'est une régénération de plus, et elle va dans le sens prudent — vers
    « regarde », jamais vers « laisse passer ».

    Ce que cela ne change pas, et qui est la vraie protection : la surcharge
    n'est pas un fichier de déploiement. Elle n'est ni dans `deploy/**`, ni
    recensée parmi les fichiers Compose du système livré. Un lecteur de
    l'inventaire ne doit pas pouvoir croire que le laboratoire tourne avec ses
    limiteurs de débit désactivés.
    """
    import json

    from scripts.g0_provenance import fichiers_entree

    assert SURCHARGE.is_file(), "la surcharge de mesure a disparu"
    assert not (REPO_ROOT / "deploy" / "g0-perf-overlay.yml").exists()
    assert SURCHARGE in fichiers_entree("performance")

    inventaire = json.loads(
        (REPO_ROOT / "artifacts" / "g0" / "inventory.json").read_text(encoding="utf-8")
    )["payload"]
    recenses = {entree["file"] for entree in inventaire["compose"]}
    assert SURCHARGE.name not in recenses, (
        "la surcharge de mesure est recensee parmi les fichiers Compose du "
        "systeme livre : l'inventaire decrirait une stack sans limiteurs"
    )
    assert "docker-compose.yml" in recenses, (
        "aucun fichier Compose recense : l'assertion precedente ne prouverait rien"
    )


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


def _releve_pendant_la_charge() -> dict[str, Any]:
    """Un relevé de ressources valide, tel que l'échantillonneur en produit.

    Les valeurs de CPU et de mémoire sont quelconques : aucun contrôle ne porte
    sur elles, et il ne faut jamais en introduire. Ce qui est vérifié, c'est
    que la mesure a EU LIEU, pendant la charge, sur les conteneurs attendus.
    """
    from scripts.g0_perf_baseline import charger_plan

    reglage = charger_plan()["performance"]["resource_sampling"]
    return {
        "enabled": True,
        "sampler_started_at": "2026-09-09T00:00:00.000000Z",
        "sampler_stopped_at": "2026-09-09T00:01:00.000000Z",
        "load_window_seconds": 58.0,
        "interval_seconds_configured": reglage["interval_seconds"],
        "interval_seconds_observed_mean": 1.2,
        "samples_total": 50,
        "samples_within_load_window": 48,
        "samples_before_load_window": 1,
        "samples_after_load_window": 1,
        "sampler_alive_at_stop": True,
        "sampler_exception": None,
        "sampling_errors": [],
        "containers": {
            service: {
                "samples": 48,
                "cpu_percent": {"mean": 42.0, "p95": 81.5, "max": 96.0},
                "memory_bytes": {
                    "mean": 200_000_000,
                    "p95": 260_000_000,
                    "max": 280_000_000,
                },
            }
            for service in reglage["observed_containers"]
        },
    }


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
        charger_plan,
        empreinte_plan,
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
    # La fixture DERIVE du plan au lieu de recopier ses valeurs. Recopiees,
    # elles auraient continue de decrire `[1, 3]` pendant que le plan serait
    # passe a autre chose, et le temoin aurait valide une campagne que le
    # validateur refuse en CI.
    plan = charger_plan()["performance"]
    return {
        "run": {
            "run_id": "abcdef0123",
            "seed": plan["seed"],
            "started_at": "2026-09-09T00:00:00Z",
            "duration_seconds": 120.0,
            "concurrency_levels": list(plan["concurrency"]),
            "repetitions": plan["repetitions"],
            "iterations_per_worker": plan["iterations"],
            "warmup_iterations_per_worker": plan["warmup"],
            "scenario_order": [s.nom for s in noms],
            "scenario_sha256": empreinte_scenario(),
            "percentile_method": "nearest-rank (ceil(p/100*n)) sans interpolation",
            "clock_source": "time.perf_counter (monotone)",
            "clock_monotonic": True,
            "retries": 0,
            "measurement_plan": "scripts/g0_quality_plan.json",
            "measurement_plan_sha256": empreinte_plan(),
            "performance_profile": plan["profile"],
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
            str(niveau): {
                "concurrency": niveau,
                "repetitions": [{"index": i} for i in range(plan["repetitions"])],
                "wall_clock_seconds": 60.0,
                "scenarios": copy.deepcopy(scenarios),
                "aggregate": copy.deepcopy(agregat),
                "resources": {
                    "before": {},
                    "after": {},
                    "during_load": _releve_pendant_la_charge(),
                    "postgres_delta": {"available": False},
                },
            }
            for niveau in plan["concurrency"]
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
        "validity_policy": {
            "min_samples_per_scenario_per_level": plan["minimum_samples"],
        },
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
    """1, 3, 5, 10 — 3 est le premier usage envisagé au CSA GR Plateau.

    Les niveaux viennent du PLAN, plus d'une constante du module : le contrôle
    porte donc sur le fichier réellement sous empreinte. Une constante locale
    aurait pu rester à `(1, 3, 5, 10)` pendant que la campagne tournait à un
    seul niveau.
    """
    from scripts.g0_perf_baseline import charger_plan

    assert charger_plan()["performance"]["concurrency"] == [1, 3, 5, 10]


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


# ══════════════════════════════════════════════════════════════════════════
# Dépendances de mesure contre dépendances du produit
# ══════════════════════════════════════════════════════════════════════════
#
# `requirements.txt` est installé dans le virtualenv copié dans l'image
# runtime. Y épingler `coverage[toml]` et `pytest-cov` faisait embarquer un
# instrumenteur de code dans l'image expédiée — un outil capable de tracer
# chaque ligne exécutée, qu'aucun flux clinique n'appelle jamais.
#
# Chaque mutation ci-dessous est précédée de son témoin : le contrôle doit
# accepter l'état intact, sans quoi un contrôle qui refuse tout passerait pour
# vigilant.


@pytest.fixture
def requirements_runtime() -> Path:
    return REPO_ROOT / "requirements.txt"


@pytest.fixture
def requirements_qualite() -> Path:
    return REPO_ROOT / "requirements-g0-quality.txt"


def _avec_contenu(chemin: Path, contenu: str):
    """Remplace temporairement un fichier, et le restaure quoi qu'il arrive."""
    import contextlib

    @contextlib.contextmanager
    def gestionnaire():
        original = chemin.read_text(encoding="utf-8")
        try:
            chemin.write_text(contenu, encoding="utf-8")
            yield
        finally:
            chemin.write_text(original, encoding="utf-8")

    return gestionnaire()


def test_temoin_les_dependances_intactes_sont_acceptees():
    """Témoin. Sans lui, les mutations qui suivent ne prouveraient rien."""
    from scripts.g0_coverage_summary import controler_dependances

    assert controler_dependances() == []


def test_mutation_coverage_remis_dans_le_runtime_est_refusee(requirements_runtime):
    """L'image expédiée ne doit pas embarquer d'instrumenteur de code."""
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_runtime.read_text(encoding="utf-8") + "\ncoverage[toml]==7.16.0\n"
    with _avec_contenu(requirements_runtime, contenu):
        ecarts = controler_dependances()
    assert any("coverage" in e and "image runtime" in e for e in ecarts), ecarts


def test_mutation_pytest_cov_remis_dans_le_runtime_est_refusee(requirements_runtime):
    """Même défaut, autre paquet : le contrôle ne doit pas viser un seul nom."""
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_runtime.read_text(encoding="utf-8") + "\npytest-cov==7.1.0\n"
    with _avec_contenu(requirements_runtime, contenu):
        ecarts = controler_dependances()
    assert any("pytest-cov" in e and "image runtime" in e for e in ecarts), ecarts


def test_mutation_coverage_sans_extra_dans_le_runtime_est_refusee(requirements_runtime):
    """`coverage==7.16.0` et `coverage[toml]==7.16.0` sont la même distribution.

    Comparer les lignes brutes aurait laissé passer la première : elle ne
    ressemble pas à la chaîne cherchée, et elle installe pourtant le même
    module dans la même image.
    """
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_runtime.read_text(encoding="utf-8") + "\ncoverage==7.16.0\n"
    with _avec_contenu(requirements_runtime, contenu):
        ecarts = controler_dependances()
    assert any("coverage" in e and "image runtime" in e for e in ecarts), ecarts


def test_mutation_version_non_epinglee_est_refusee(requirements_qualite):
    """Une plage de versions ferait bouger la baseline sans qu'aucun code ne change."""
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_qualite.read_text(encoding="utf-8").replace(
        "coverage[toml]==7.16.0", "coverage[toml]>=7.16.0"
    )
    with _avec_contenu(requirements_qualite, contenu):
        ecarts = controler_dependances()
    assert any("non epingle" in e for e in ecarts), ecarts


def test_mutation_fichier_qualite_sans_include_du_runtime_est_refusee(requirements_qualite):
    """Sans `-r requirements.txt`, les deux jeux de versions divergeraient."""
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_qualite.read_text(encoding="utf-8").replace(
        "-r requirements.txt", "# -r requirements.txt"
    )
    with _avec_contenu(requirements_qualite, contenu):
        ecarts = controler_dependances()
    assert any("n'inclut pas requirements.txt" in e for e in ecarts), ecarts


def test_mutation_paquet_absent_du_fichier_qualite_est_refusee(requirements_qualite):
    """Retirer l'outil du fichier qui doit le porter est aussi un défaut."""
    from scripts.g0_coverage_summary import controler_dependances

    contenu = requirements_qualite.read_text(encoding="utf-8").replace("pytest-cov==7.1.0", "")
    with _avec_contenu(requirements_qualite, contenu):
        ecarts = controler_dependances()
    assert any("absent de" in e for e in ecarts), ecarts


def test_le_dockerfile_n_installe_que_les_dependances_du_produit():
    """Le fichier de qualité ne doit jamais entrer dans l'image."""
    dockerfile = _lire(REPO_ROOT / "Dockerfile")
    assert "requirements.txt" in dockerfile
    assert "requirements-g0-quality.txt" not in dockerfile, (
        "le Dockerfile installe l'outillage de mesure dans l'image expediee"
    )


def test_le_job_couverture_installe_le_fichier_de_qualite():
    """Un job qui installerait `requirements.txt` seul n'aurait pas `coverage`."""
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    etapes = workflow["jobs"]["coverage-baseline"]["steps"]
    installations = [
        str(e.get("run", "")) for e in etapes if "pip install" in str(e.get("run", ""))
    ]
    assert installations, "le job couverture n'installe rien"
    assert any("requirements-g0-quality.txt" in cmd for cmd in installations), (
        "le job couverture n'installe pas le fichier de qualite : coverage serait absent"
    )
    # Le cache doit couvrir les DEUX fichiers, sans quoi il serait réutilisé
    # après un changement de version de l'outil de mesure.
    mise_en_place = next(e for e in etapes if "setup-python" in str(e.get("uses", "")))
    cache = str(mise_en_place["with"]["cache-dependency-path"])
    assert "requirements.txt" in cache and "requirements-g0-quality.txt" in cache


def test_l_image_runtime_est_verifiee_par_la_ci_et_pas_seulement_par_un_fichier():
    """Un paquet apporté transitivement ne se lirait dans aucun `requirements`.

    Le contrôle de fichiers ne voit que ce qui est déclaré. L'image, elle, peut
    recevoir un module par une dépendance de dépendance. La CI doit donc
    INTERROGER l'image construite, et le job doit échouer si elle le porte.
    """
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    etapes = workflow["jobs"]["coverage-baseline"]["steps"]
    corps = "\n".join(str(e.get("run", "")) for e in etapes)
    assert "docker build" in corps, "l'image runtime n'est jamais construite dans ce job"
    assert "find_spec" in corps, "aucune interrogation de l'image construite"
    for module in ("coverage", "pytest_cov"):
        assert module in corps, f"{module} n'est pas cherche dans l'image"


# ══════════════════════════════════════════════════════════════════════════
# Le plan de mesure — les paramètres sont sous empreinte
# ══════════════════════════════════════════════════════════════════════════
#
# Le workflow FIXAIT la mesure : concurrences, répétitions, graine, warm-up,
# liste des tests PostgreSQL. La provenance déclarait pourtant `.github/**`
# volontairement absent au motif que « la CI orchestre la mesure, elle ne la
# détermine pas ». Remplacer `--concurrency 1,3,5,10` par `--concurrency 1`
# changeait donc la mesure sans changer aucune empreinte.


def test_le_plan_de_mesure_entre_dans_les_deux_empreintes():
    """Sinon il ne serait qu'une documentation de plus."""
    from scripts.g0_provenance import ENSEMBLES_ENTREE, fichiers_entree

    plan = REPO_ROOT / "scripts" / "g0_quality_plan.json"
    assert plan.is_file()
    for ensemble in ("coverage", "performance"):
        assert "scripts/g0_quality_plan.json" in ENSEMBLES_ENTREE[ensemble]
        assert plan in fichiers_entree(ensemble), f"plan absent de l'ensemble {ensemble}"


@pytest.mark.parametrize("ensemble", ["coverage", "performance"])
def test_mutation_plan_modifie_sans_changement_dempreinte_est_refusee(ensemble):
    """Preuve que le plan est LU, et pas seulement listé."""
    from scripts.g0_provenance import empreinte_entrees

    plan = REPO_ROOT / "scripts" / "g0_quality_plan.json"
    avant, _ = empreinte_entrees(ensemble)
    original = plan.read_bytes()
    try:
        plan.write_bytes(original.replace(b'"repetitions": 3', b'"repetitions": 1'))
        apres, _ = empreinte_entrees(ensemble)
    finally:
        plan.write_bytes(original)
    assert apres != avant, f"l'empreinte {ensemble} ignore le plan : elle ne le lit pas"
    assert plan.read_bytes() == original


def test_le_workflow_ne_fixe_plus_les_parametres_de_charge():
    """Le job ne doit plus porter ce que le plan détermine.

    Si un seul de ces drapeaux revenait dans la ligne de commande, la mesure
    pourrait à nouveau s'écarter du fichier sous empreinte — et le commentaire
    du workflow qui affirme le contraire deviendrait faux.
    """
    import yaml

    # Le controle porte sur les COMMANDES, jamais sur le texte du fichier : le
    # commentaire qui explique ce defaut cite lui-meme `--concurrency`, et un
    # grep sur tout le fichier se declencherait sur sa propre explication.
    # C'est exactement l'erreur qu'un `grep -r fail_under` avait deja commise
    # ailleurs dans cette campagne.
    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    commandes = chr(10).join(
        str(etape.get("run", "")) for job in workflow["jobs"].values() for etape in job["steps"]
    )
    assert "g0_perf_baseline.py --run" in commandes, "le banc n'est plus lance : rien a controler"
    for drapeau in (
        "--concurrency",
        "--repetitions",
        "--iterations",
        "--warmup",
        "--seed",
        "--min-samples",
    ):
        assert drapeau not in commandes, (
            f"{drapeau} est encore passe par le workflow : la mesure ne suit plus le plan"
        )


def test_le_job_couverture_lit_la_liste_des_tests_postgres_dans_le_plan():
    """Écrite dans le job, la restreindre n'aurait changé aucune empreinte."""
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    etape = next(
        e
        for e in workflow["jobs"]["coverage-baseline"]["steps"]
        if "PostgreSQL" in str(e.get("name", ""))
    )
    # Les COMMENTAIRES shell sont retires avant le controle. Sans cela, une
    # etape qui reecrirait la liste en dur tout en laissant l'ancienne ligne
    # commentee passerait : la chaine cherchee serait encore presente, et le
    # test se declencherait sur une ligne qui ne s'execute pas. C'est la meme
    # erreur qu'un `grep` sur un fichier entier.
    effectif = chr(10).join(
        ligne for ligne in str(etape["run"]).splitlines() if not ligne.strip().startswith("#")
    )
    assert "g0_quality_plan.json" in effectif, "la liste est encore ecrite dans le job"
    assert "postgres_test_files" in effectif
    # Et aucun fichier de test ne doit etre nomme en dur dans la commande.
    assert "_postgres.py" not in effectif, (
        "un fichier de test PostgreSQL est nomme en dur dans le job : la liste "
        "pourrait etre restreinte sans changer aucune empreinte"
    )
    # Et le plan doit réellement porter les fichiers, qui doivent exister.
    from scripts.g0_coverage_summary import charger_plan

    fichiers = charger_plan()["coverage"]["postgres_test_files"]
    assert len(fichiers) >= 9, fichiers
    for chemin in fichiers:
        assert (REPO_ROOT / chemin).is_file(), f"{chemin} declare au plan mais absent"


def test_les_commandes_instrumentees_mesurent_toutes_les_branches():
    """`--cov-branch` doit figurer dans CHAQUE commande qui collecte.

    La protection de fond existe deja en aval : `controler()` refuse un rapport
    dont `branch_coverage` est faux. Mais elle n'intervient qu'apres toute la
    campagne, et le message parle du rapport, pas de la commande. Ce controle
    statique nomme la cause au lieu du symptome.

    Le defaut a ete trouve par mutation : retirer `--cov-branch` du workflow ne
    faisait echouer aucun test.
    """
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    etapes = workflow["jobs"]["coverage-baseline"]["steps"]
    collectes = [
        chr(10).join(
            ligne
            for ligne in str(etape.get("run", "")).splitlines()
            if not ligne.strip().startswith("#")
        )
        for etape in etapes
        if "--cov=app" in str(etape.get("run", ""))
    ]
    assert len(collectes) >= 2, "moins de deux commandes instrumentees : la mesure a maigri"
    for commande in collectes:
        assert "--cov-branch" in commande, (
            "une commande collecte sans mesurer les branches : le chiffre de "
            "branches serait incomplet sans que rien ne le dise"
        )
    # Le processus applicatif du flux E2E aussi.
    e2e = next(e for e in etapes if "E2E" in str(e.get("name", "")))
    assert "--branch" in str(e2e["run"]), "l'application E2E tourne sans mesure de branches"


def test_mutation_echantillonnage_desactive_dans_le_plan_est_refusee(mesure, monkeypatch):
    """Le plan ne peut pas se dispenser lui-meme d'une preuve exigee.

    Trouvee par mutation : `"enabled": false` dans le plan n'avait AUCUN effet.
    Le validateur lisait ce champ dans le rapport, que l'echantillonneur pose
    toujours a vrai. Un champ qui a l'apparence d'un interrupteur sans en etre
    un est pire qu'un champ absent — on croit avoir agi.
    """
    from scripts import g0_perf_baseline as banc

    plan_modifie = banc.charger_plan()
    plan_modifie["performance"]["resource_sampling"]["enabled"] = False
    monkeypatch.setattr(banc, "charger_plan", lambda: plan_modifie)
    motifs = banc.valider(mesure)
    assert any("echantillonnage des ressources desactive" in m for m in motifs), motifs


def test_mutation_aucun_conteneur_requis_au_plan_est_refusee(mesure, monkeypatch):
    """Vider la liste des conteneurs requis viderait le controle de son objet."""
    from scripts import g0_perf_baseline as banc

    plan_modifie = banc.charger_plan()
    plan_modifie["performance"]["resource_sampling"]["required_containers"] = []
    monkeypatch.setattr(banc, "charger_plan", lambda: plan_modifie)
    motifs = banc.valider(mesure)
    assert any("aucun conteneur requis" in m for m in motifs), motifs


def test_mutation_resume_citant_un_autre_plan_est_refusee(resume_couverture):
    """Une campagne doit citer le plan présent dans l'arbre, pas un autre."""
    from scripts.g0_coverage_summary import controler

    resume_couverture["payload"]["measurement"]["measurement_plan_sha256"] = "0" * 64
    assert any("ne cite pas le plan" in e for e in controler(resume_couverture))


def test_mutation_mesure_citant_un_autre_plan_est_refusee(mesure):
    """Le même contrôle, côté performance."""
    from scripts.g0_perf_baseline import valider

    mesure["run"]["measurement_plan_sha256"] = "0" * 64
    assert any("ne cite pas le plan" in m for m in valider(mesure))


@pytest.mark.parametrize(
    ("champ", "valeur", "attendu"),
    [
        ("concurrency_levels", [1], "concurrency"),
        ("repetitions", 1, "repetitions"),
        ("iterations_per_worker", 1, "iterations"),
        ("warmup_iterations_per_worker", 0, "warmup"),
        ("seed", 1, "seed"),
    ],
)
def test_mutation_parametre_hors_plan_est_refusee(mesure, champ, valeur, attendu):
    """Une ligne de commande ne doit plus pouvoir restreindre la mesure.

    C'est la contrepartie indispensable du plan : sans ce contrôle, le plan
    resterait une intention, et une campagne réduite continuerait de le citer.
    """
    from scripts.g0_perf_baseline import valider

    mesure["run"][champ] = valeur
    motifs = valider(mesure)
    assert any("hors plan" in m and attendu in m for m in motifs), motifs


def test_mutation_profil_de_mesure_different_du_plan_est_refusee(mesure):
    """Le profil dit dans quel régime la mesure a eu lieu. Il ne s'invente pas."""
    from scripts.g0_perf_baseline import valider

    mesure["run"]["performance_profile"] = "PRODUCTION"
    assert any("profil de mesure" in m for m in valider(mesure))


def test_le_profil_declare_dit_que_les_limiteurs_sont_desactives():
    """Une baseline mesurée limiteurs coupés ne décrit pas le futur site."""
    from scripts.g0_perf_baseline import charger_plan

    plan = charger_plan()["performance"]
    assert plan["profile"] == "CORE_INTRINSIC_WITH_RATE_LIMITS_DISABLED"
    assert plan["rate_limits_enabled"] is False


# ══════════════════════════════════════════════════════════════════════════
# Ressources PENDANT la charge
# ══════════════════════════════════════════════════════════════════════════
#
# La campagne précédente encadrait chaque niveau de deux `docker stats` : elle
# mesurait le repos, juste avant que la charge monte et juste après qu'elle
# était retombée, et publiait le résultat comme s'il décrivait l'effort.
#
# Aucun seuil de CPU ni de mémoire n'est introduit ici, et il ne faut jamais en
# ajouter : une consommation élevée est un RÉSULTAT. C'est l'ABSENCE de mesure
# qui invalide la campagne.


def test_temoin_un_releve_de_ressources_complet_est_accepte(mesure):
    """Témoin de la série qui suit."""
    from scripts.g0_perf_baseline import valider

    assert valider(mesure) == []


def test_mutation_aucun_echantillon_de_ressources_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["samples_total"] = 0
        niveau["resources"]["during_load"]["samples_within_load_window"] = 0
    motifs = valider(mesure)
    assert any("zero echantillon" in m for m in motifs), motifs


def test_mutation_echantillons_tous_anterieurs_a_la_charge_est_refusee(mesure):
    """L'échantillonneur a tourné, mais pas pendant l'effort. C'est le défaut exact."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        pendant = niveau["resources"]["during_load"]
        pendant["samples_within_load_window"] = 0
        pendant["samples_before_load_window"] = 50
        pendant["samples_after_load_window"] = 0
    motifs = valider(mesure)
    assert any("aucun echantillon dans la fenetre" in m for m in motifs), motifs


def test_mutation_echantillons_tous_posterieurs_a_la_charge_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        pendant = niveau["resources"]["during_load"]
        pendant["samples_within_load_window"] = 0
        pendant["samples_before_load_window"] = 0
        pendant["samples_after_load_window"] = 50
    motifs = valider(mesure)
    assert any("aucun echantillon dans la fenetre" in m for m in motifs), motifs


def test_mutation_trop_peu_dechantillons_pendant_la_charge_est_refusee(mesure):
    """Une moyenne et un p95 sur un point ne signifient rien."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["samples_within_load_window"] = 1
    motifs = valider(mesure)
    assert any("pendant la charge" in m and "signifient rien" in m for m in motifs), motifs


def test_mutation_fenetre_de_charge_vide_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["load_window_seconds"] = 0.0
    motifs = valider(mesure)
    assert any("fenetre de charge vide" in m for m in motifs), motifs


def test_mutation_cpu_absent_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["containers"]["app"]["cpu_percent"]["mean"] = None
    motifs = valider(mesure)
    assert any("sans CPU pendant la charge" in m for m in motifs), motifs


def test_mutation_memoire_absente_est_refusee(mesure):
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["containers"]["postgres"]["memory_bytes"]["mean"] = None
    motifs = valider(mesure)
    assert any("sans memoire pendant la charge" in m for m in motifs), motifs


@pytest.mark.parametrize("service", ["app", "postgres", "valkey", "proxy"])
def test_mutation_conteneur_attendu_non_mesure_est_refusee(mesure, service):
    """Les quatre conteneurs du chemin d'une requête, un par un."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"]["during_load"]["containers"].pop(service, None)
    motifs = valider(mesure)
    assert any(f"`{service}` attendu, jamais mesure" in m for m in motifs), motifs


def test_mutation_echantillonneur_mort_prematurement_est_refusee(mesure):
    """Une série tronquée a l'air normale. Rien ne la trahirait sans ce champ."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        pendant = niveau["resources"]["during_load"]
        pendant["sampler_alive_at_stop"] = False
        pendant["sampler_exception"] = "RuntimeError: docker indisponible"
    motifs = valider(mesure)
    assert any("mort avant la fin" in m for m in motifs), motifs


def test_mutation_releve_de_ressources_absent_est_refusee(mesure):
    """Revenir aux deux instantanés `before`/`after` doit être refusé."""
    from scripts.g0_perf_baseline import valider

    for niveau in mesure["levels"].values():
        niveau["resources"] = {"before": {}, "after": {}}
    motifs = valider(mesure)
    assert any("aucune mesure de ressources pendant la charge" in m for m in motifs), motifs


def test_aucun_seuil_de_cpu_ni_de_memoire_nulle_part():
    """Une consommation élevée est un constat. G0 ne juge pas."""
    for chemin in (
        REPO_ROOT / "scripts" / "g0_perf_baseline.py",
        REPO_ROOT / "scripts" / "g0_quality_plan.json",
        REPO_ROOT / ".github" / "workflows" / "g0-quality.yml",
    ):
        source = _lire(chemin)
        for interdit in (
            "MAX_CPU",
            "CPU_BUDGET",
            "max_memory_bytes",
            "MEMORY_LIMIT_PERCENT",
            "cpu_threshold",
            "memory_threshold",
        ):
            assert interdit not in source, f"{interdit} dans {chemin.name}"


def test_les_parseurs_de_docker_stats_lisent_ce_que_docker_ecrit():
    """Sur les formats réels de `docker stats`, et sur ce qu'il rend illisible.

    Sans ce test, un parseur qui renverrait toujours `None` ferait échouer la
    campagne pour la bonne raison affichée et la mauvaise raison réelle.
    """
    from scripts.g0_perf_baseline import _octets_memoire, _pourcentage_cpu

    assert _pourcentage_cpu("12.34%") == 12.34
    assert _pourcentage_cpu("0.00%") == 0.0
    assert _pourcentage_cpu("--") is None
    assert _pourcentage_cpu(None) is None

    assert _octets_memoire("123.4MiB / 7.775GiB") == int(123.4 * 2**20)
    assert _octets_memoire("1GiB / 2GiB") == 2**30
    assert _octets_memoire("512B / 2GiB") == 512
    assert _octets_memoire("-- / --") is None
    assert _octets_memoire(None) is None


def test_lechantillonneur_ne_retient_que_les_echantillons_de_la_fenetre(monkeypatch):
    """Le comptage doit refléter la fenêtre, pas la durée totale du fil.

    L'échantillonneur est exercé pour de bon — `_docker` est remplacé, le fil
    tourne, et le rapport est confronté à une fenêtre choisie. Un test qui
    n'inspecterait que le dictionnaire produit ne dirait rien du fil.
    """
    import json as _json
    import time as _time

    from scripts import g0_perf_baseline as banc

    compteur = {"n": 0}

    def faux_docker(*arguments, timeout=60):
        compteur["n"] += 1
        return _json.dumps(
            {"ID": "abcdef123456", "CPUPerc": "50.00%", "MemUsage": "100MiB / 1GiB", "PIDs": "7"}
        )

    monkeypatch.setattr(banc, "_docker", faux_docker)
    echantillonneur = banc.EchantillonneurRessources({"app": "abcdef123456"}, 0.05)
    echantillonneur.demarrer()
    debut = _time.perf_counter()
    while compteur["n"] < 4:
        _time.sleep(0.02)
    fin = _time.perf_counter()
    echantillonneur.arreter()

    rapport = echantillonneur.rapport(charge_debut=debut, charge_fin=fin)
    assert rapport["sampler_alive_at_stop"] is True
    assert rapport["samples_total"] >= 3
    assert rapport["samples_within_load_window"] >= 1
    assert rapport["containers"]["app"]["cpu_percent"]["mean"] == 50.0
    assert rapport["containers"]["app"]["memory_bytes"]["max"] == 100 * 2**20

    # Une fenêtre qui ne recouvre rien doit se voir dans le comptage, et non
    # produire des chiffres d'allure normale.
    hors = echantillonneur.rapport(charge_debut=fin + 100, charge_fin=fin + 200)
    assert hors["samples_within_load_window"] == 0
    assert hors["containers"]["app"]["cpu_percent"]["mean"] is None


def test_lechantillonneur_signale_sa_propre_mort(monkeypatch):
    """Un fil mort en cours de route ne doit pas passer pour un fil silencieux."""
    from scripts import g0_perf_baseline as banc

    def docker_qui_explose(*arguments, timeout=60):
        raise RuntimeError("docker a disparu")

    monkeypatch.setattr(banc, "_docker", docker_qui_explose)
    echantillonneur = banc.EchantillonneurRessources({"app": "abcdef123456"}, 0.05)
    echantillonneur.demarrer()
    import time as _time

    _time.sleep(0.2)
    echantillonneur.arreter()
    rapport = echantillonneur.rapport(charge_debut=0.0, charge_fin=1e12)
    assert rapport["sampler_alive_at_stop"] is False
    assert "docker a disparu" in str(rapport["sampler_exception"])


# ══════════════════════════════════════════════════════════════════════════
# Identités mesurées — tête de PR, base, commit de fusion, arbre
# ══════════════════════════════════════════════════════════════════════════


def test_le_workflow_distingue_la_tete_de_pr_du_commit_de_fusion():
    """Sur un `pull_request`, `GITHUB_SHA` est le commit de fusion synthétique.

    Les confondre ferait citer par la campagne un commit qui n'existe sur
    aucune référence, et que personne ne pourrait retrouver après coup.
    """
    workflow = _lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml")
    assert "github.event.pull_request.head.sha" in workflow
    assert "github.event.pull_request.base.sha" in workflow
    for champ in (
        "pr_head_sha",
        "base_sha",
        "tested_merge_sha",
        "tested_tree_sha",
        "workflow_run_id",
    ):
        assert champ in workflow, f"{champ} n'est pas enregistre"


def test_les_deux_jobs_enregistrent_les_identites_mesurees():
    """Une campagne qui ne dit pas sur quoi elle a porté ne se rejoue pas."""
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    for job in ("coverage-baseline", "performance-baseline"):
        corps = "\n".join(str(e.get("run", "")) for e in workflow["jobs"][job]["steps"])
        assert "pr_head_sha" in corps, f"{job} n'enregistre pas la tete de la PR"
        assert "tested_tree_sha" in corps, f"{job} n'enregistre pas l'arbre teste"
        assert "github.run_id" in corps, f"{job} n'enregistre pas l'identifiant d'execution"


def test_le_workflow_ne_publie_toujours_aucune_image_et_ne_cree_aucun_tag():
    """Un job qui mesure ne doit rien pouvoir publier."""
    import yaml

    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml"))
    assert workflow["permissions"] == {"contents": "read"}
    texte = _lire(REPO_ROOT / ".github" / "workflows" / "g0-quality.yml")
    for interdit in (
        "docker push",
        "gh release",
        "actions/create-release",
        "git tag",
        "packages: write",
        "contents: write",
    ):
        assert interdit not in texte, f"{interdit} present dans le workflow de mesure"

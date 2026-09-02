"""Tests — Grafana est hors du cœur, et l'absence de Grafana n'est pas un défaut.

Le mode nominal supporté de RUGGYLAB est « Core sans Grafana ». Ce n'est pas une
préférence de déploiement : c'est ce qui fait que RUGGYLAB ne distribue aucune
œuvre AGPL-3.0. Une réintroduction dans la stack principale rétablirait
l'obligation sans que personne s'en aperçoive — d'où ces tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = "docker-compose.yml"
OVERLAY = "docker-compose.monitoring.yml"
OVERLAY_DEV = "docker-compose.monitoring.dev.yml"

GRAFANA_TAG = "11.0.0"
GRAFANA_DIGEST = "sha256:0dc5a246ab16bb2c38a349fb588174e832b4c6c2db0981d0c3e6cd774ba66a54"

#: Fonctions que le cœur doit assurer sans Grafana.
_FONCTIONS_COEUR = (
    "app",
    "postgres",
    "prometheus",
    "proxy",
    "scheduler",
    "analyzer-gateway",
    "db-backup",
)


def _lire(chemin: str) -> str:
    return (REPO_ROOT / chemin).read_text(encoding="utf-8")


def _charger(chemin: str) -> dict:
    return yaml.safe_load(_lire(chemin))


@pytest.fixture(scope="module")
def base() -> dict:
    return _charger(BASE)


@pytest.fixture(scope="module")
def overlay() -> dict:
    return _charger(OVERLAY)


# ── le cœur ne contient plus Grafana ────────────────────────────────────────


def test_the_core_stack_has_no_grafana_service(base):
    assert "grafana" not in base["services"]


def test_the_core_stack_has_no_grafana_volume(base):
    assert "grafana_data" not in (base.get("volumes") or {})


def test_the_core_compose_file_never_mentions_grafana():
    """Même en commentaire : la moindre variable rendrait le démarrage exigeant."""
    assert "grafana" not in _lire(BASE).lower()


def test_no_core_service_depends_on_grafana(base):
    for nom, service in base["services"].items():
        depends = service.get("depends_on") or {}
        assert "grafana" not in depends, f"{nom} dépend encore de Grafana"


def test_the_core_starts_without_any_grafana_variable():
    """`GRAFANA_PASSWORD` était obligatoire : un `up` échouait sans elle."""
    contenu = _lire(BASE)
    for variable in ("GRAFANA_PASSWORD", "GRAFANA_USER"):
        assert variable not in contenu, f"{variable} encore exigée par la stack principale"


@pytest.mark.parametrize("service", _FONCTIONS_COEUR)
def test_the_core_still_provides_every_supported_function(base, service):
    """Retirer Grafana ne doit avoir retiré rien d'autre."""
    assert service in base["services"], f"{service} a disparu du cœur"


def test_prometheus_stays_in_the_core(base):
    """RUGGYLAB → /metrics → Prometheus doit fonctionner sans Grafana."""
    prometheus = base["services"]["prometheus"]
    assert "backend_net" in prometheus["networks"], "Prometheus doit pouvoir scraper app:8000"
    assert "app" in prometheus["depends_on"]


# ── l'overlay existe, et il est correctement borné ──────────────────────────


def test_the_overlay_provides_grafana(overlay):
    assert "grafana" in overlay["services"]
    assert "grafana_data" in overlay["volumes"]


def test_the_overlay_image_is_pinned_by_tag_and_digest(overlay):
    image = overlay["services"]["grafana"]["image"]
    assert image.startswith(f"grafana/grafana:{GRAFANA_TAG}@"), image
    assert image.endswith(GRAFANA_DIGEST), "un tag est mutable, un digest non"


def test_the_overlay_uses_the_official_registry(overlay):
    """Ni copie, ni reconditionnement, ni republication comme actif RUGGYLAB."""
    image = overlay["services"]["grafana"]["image"]
    assert image.startswith("grafana/grafana:"), image
    assert "ghcr.io" not in image and "ruggylab" not in image.lower()


def test_the_overlay_publishes_no_port(overlay):
    """Accès par VPN/bastion — jamais le VLAN clinique."""
    assert "ports" not in overlay["services"]["grafana"]


def test_the_development_override_binds_to_loopback_only():
    ports = _charger(OVERLAY_DEV)["services"]["grafana"]["ports"]
    for mapping in ports:
        assert str(mapping).startswith("127.0.0.1:"), f"exposition non locale : {mapping}"


def test_the_overlay_states_the_agpl_nature(overlay):
    texte = _lire(OVERLAY)
    assert "AGPL-3.0" in texte
    assert "ne fait PAS partie du cœur distribué" in texte


def test_dashboards_are_mounted_read_only(overlay):
    """Les tableaux de bord sont de la configuration, pas une œuvre dérivée."""
    montages = overlay["services"]["grafana"]["volumes"]
    provisioning = [m for m in montages if "provisioning" in m]
    assert provisioning and all(m.endswith(":ro") for m in provisioning)


# ── la CI prouve les deux scénarios, et n'en rend qu'un bloquant ────────────


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(_lire(".github/workflows/ci.yml"))


def test_the_core_scenario_asserts_the_absence_of_grafana(ci):
    etapes = ci["jobs"]["docker-stack"]["steps"]
    etape = next(s for s in etapes if "ships no Grafana" in str(s.get("name", "")))
    script = etape["run"]
    assert "docker compose ps --services" in script
    assert "docker image ls" in script


def test_the_overlay_scenario_exists_and_is_verified(ci):
    noms = [str(s.get("name", "")) for s in ci["jobs"]["monitoring-overlay"]["steps"]]
    for attendu in (
        "Wait for Grafana to become healthy",
        "Assert the Prometheus datasource is provisioned",
        "Assert the RUGGYLAB dashboards are loaded",
        "Remove Grafana and assert RUGGYLAB is unaffected",
    ):
        assert attendu in noms, f"contrôle absent de l'overlay : {attendu}"


def test_the_overlay_scenario_does_not_gate_the_core(ci):
    """Un cœur sain ne doit pas dépendre d'un composant que RUGGYLAB ne distribue pas."""
    assert "monitoring-overlay" not in ci["jobs"]["deploy"]["needs"]
    assert "monitoring-overlay" not in ci["jobs"]["release"]["needs"]


def test_the_blocking_scenario_still_gates_the_core(ci):
    assert "docker-stack" in ci["jobs"]["deploy"]["needs"]


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

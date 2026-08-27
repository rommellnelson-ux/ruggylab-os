"""Tests — exposition réseau des ports automates (§8.1).

Les ports automates parlent des protocoles sans authentification ni
chiffrement et transportent identités patient et résultats. La seule barrière
est le confinement réseau : ces tests verrouillent le fait qu'aucune
configuration ne puisse ouvrir ces ports au-delà d'une interface nommée.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose_name: str, service: str) -> str:
    """Extrait le bloc YAML d'un service, par indentation.

    Volontairement sans PyYAML : ce paquet n'est pas une dépendance déclarée du
    projet (il n'arrive qu'en transitif de `bandit`), et un test de sécurité ne
    doit pas dépendre d'un paquet susceptible de disparaître de l'environnement.
    """
    lines = (REPO_ROOT / compose_name).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if re.match(rf"^  {re.escape(service)}:\s*$", line):
            inside = True
            continue
        if inside:
            # Fin du bloc : prochaine clé de service (2 espaces) ou de racine.
            if line.strip() and not line.startswith("    "):
                break
            out.append(line)
    assert inside, f"service {service} introuvable dans {compose_name}"
    return "\n".join(out)


def _port_mappings(block: str) -> list[str]:
    """Entrées de la liste `ports:` d'un bloc de service."""
    lines = block.splitlines()
    mappings: list[str] = []
    inside = False
    for line in lines:
        if re.match(r"^    ports:\s*$", line):
            inside = True
            continue
        if inside:
            item = re.match(r"^      - \"?([^\"#]+)\"?", line)
            if item:
                mappings.append(item.group(1).strip())
            elif line.strip() and not line.strip().startswith("#"):
                break
    return mappings


def _settings(**over) -> Settings:
    base = {
        "SECRET_KEY": "x" * 40,
        "FIRST_SUPERUSER_PASSWORD": "AVeryStrongPassword123!",
    }
    base.update(over)
    return Settings(**base)


# ── valeurs de bind refusées ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "0.0.0.0",  # noqa: S104 - valeur justement refusée
        "::",
        "*",
        "[::]",
        "",
        "   ",
    ],
)
def test_universal_bind_is_rejected(value):
    problem = _settings(ANALYZER_BIND_IP=value).analyzer_bind_ip_problem()
    assert problem is not None, f"{value!r} doit être refusé comme adresse de publication"


@pytest.mark.parametrize("value", ["automate.local", "localhost", "vlan-automates"])
def test_hostname_is_rejected(value):
    """Un nom d'hôte peut changer de résolution : seule une IP littérale est sûre."""
    assert _settings(ANALYZER_BIND_IP=value).analyzer_bind_ip_problem() is not None


@pytest.mark.parametrize("value", ["8.8.8.8", "1.1.1.1", "51.15.20.30", "2001:4860:4860::8888"])
def test_public_address_is_always_rejected(value):
    """Refus inconditionnel : aucun indicateur d'environnement ne relâche la règle."""
    assert _settings(ANALYZER_BIND_IP=value).analyzer_bind_ip_problem() is not None
    assert _settings(ANALYZER_BIND_IP=value, TESTING=True).analyzer_bind_ip_problem() is not None


# ── valeurs de bind acceptées ───────────────────────────────────────────────


@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.30.1", "192.168.10.5", "172.16.4.2", "::1"])
def test_loopback_and_private_addresses_are_accepted(value):
    assert _settings(ANALYZER_BIND_IP=value).analyzer_bind_ip_problem() is None


def test_default_is_safe():
    """Défaut du dépôt : loopback -> aucune exposition réseau par construction."""
    settings = _settings()
    assert settings.ANALYZER_BIND_IP == "127.0.0.1"
    assert settings.analyzer_bind_ip_problem() is None


# ── fail-closed au démarrage ────────────────────────────────────────────────


def test_validation_is_noop_when_no_listener_enabled():
    """Stack par défaut : aucun listener -> une valeur douteuse ne bloque rien."""
    settings = _settings(ANALYZER_BIND_IP="0.0.0.0")  # noqa: S104 - test
    assert settings.analyzer_listeners_enabled is False
    settings.validate_analyzer_network()  # ne lève pas


@pytest.mark.parametrize(
    "listener",
    [
        "ENABLE_DH36_LISTENER",
        "ANALYZER_RAW_LISTENER_ENABLED",
        "ANALYZER_HEMATOLOGY_ENABLED",
        "ANALYZER_BIOCHEMISTRY_ENABLED",
        "ANALYZER_IMMUNO_ENABLED",
    ],
)
def test_enabled_listener_with_universal_bind_refuses_to_start(listener):
    settings = _settings(**{listener: True}, ANALYZER_BIND_IP="0.0.0.0")  # noqa: S104 - test
    assert settings.analyzer_listeners_enabled is True
    with pytest.raises(ValueError, match="toutes les interfaces"):
        settings.validate_analyzer_network()


def test_enabled_listener_with_public_bind_refuses_to_start():
    settings = _settings(ENABLE_DH36_LISTENER=True, ANALYZER_BIND_IP="8.8.8.8")
    with pytest.raises(ValueError, match="adresse publique"):
        settings.validate_analyzer_network()


def test_enabled_listener_with_vlan_bind_starts():
    settings = _settings(ENABLE_DH36_LISTENER=True, ANALYZER_BIND_IP="10.0.30.1")
    settings.validate_analyzer_network()  # ne lève pas


def test_empty_listener_host_refuses_to_start():
    settings = _settings(
        ENABLE_DH36_LISTENER=True, ANALYZER_BIND_IP="10.0.30.1", DH36_LISTENER_HOST=""
    )
    with pytest.raises(ValueError, match="DH36_LISTENER_HOST"):
        settings.validate_analyzer_network()


# ── invariants des fichiers compose ─────────────────────────────────────────


def test_base_stack_publishes_no_analyzer_port():
    """La stack par défaut reste conforme au NO-GO : aucun port automate publié."""
    block = _service_block("docker-compose.yml", "analyzer-gateway")
    assert _port_mappings(block) == [], "la stack de base ne doit publier aucun port automate"
    assert 'ENABLE_DH36_LISTENER: "false"' in block
    assert 'ANALYZER_RAW_LISTENER_ENABLED: "false"' in block


def test_override_never_publishes_on_all_interfaces():
    """L'override qualifié borne chaque port à ANALYZER_BIND_IP, sans repli permissif."""
    block = _service_block("docker-compose.analyzers.yml", "analyzer-gateway")
    mappings = _port_mappings(block)
    assert len(mappings) == 4, f"4 ports automates attendus, vu : {mappings}"
    for mapping in mappings:
        assert mapping.startswith("${ANALYZER_BIND_IP}:"), (
            f"{mapping} doit être borné à ANALYZER_BIND_IP"
        )
        # Aucun repli par défaut sur l'adresse de bind : pas de `:-` sur cette variable.
        assert "ANALYZER_BIND_IP:-" not in mapping, (
            f"{mapping} ne doit pas offrir de repli silencieux sur l'adresse de bind"
        )
        assert "0.0.0.0" not in mapping  # noqa: S104 - vérification


def test_override_requires_bind_ip_to_be_set():
    """`:?` -> docker compose refuse de rendre la config si ANALYZER_BIND_IP est absent."""
    raw = (REPO_ROOT / "docker-compose.analyzers.yml").read_text(encoding="utf-8")
    assert "ANALYZER_BIND_IP:?" in raw


def test_no_compose_file_publishes_on_all_interfaces():
    """Aucun fichier compose du dépôt ne publie un port automate sur 0.0.0.0."""
    files = sorted(REPO_ROOT.glob("docker-compose*.yml"))
    assert files, "aucun fichier compose trouvé — le test ne doit pas passer à vide"
    for path in files:
        raw = path.read_text(encoding="utf-8")
        for line in raw.splitlines():
            item = re.match(r"^      - \"?([^\"#]+)\"?", line)
            if item and "0.0.0.0" in item.group(1):  # noqa: S104 - vérification
                raise AssertionError(
                    f"{path.name}: {line.strip()} publie sur toutes les interfaces"
                )

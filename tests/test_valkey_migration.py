"""Tests — le serveur de cache est Valkey, et Redis 7.4 ne peut pas revenir.

Redis a quitté BSD-3-Clause à partir de la 7.4 pour un double régime
source-available qui restreint la redistribution. La décision du titulaire est
de l'écarter de la distribution. Ces tests empêchent une réintroduction
silencieuse — par un `docker-compose` recopié, une fusion malheureuse ou une
mise à jour automatisée.

Ils portent sur les **fichiers de distribution**. Les documents d'audit et
d'historique citent Redis 7.4 à dessein : ils décrivent ce qui a été écarté.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Fichiers qui définissent ce qui est réellement déployé.
_FICHIERS_DISTRIBUTION = (
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "docker-compose.analyzers.yml",
    ".github/workflows/ci.yml",
    "scripts/qualify_stack.sh",
)

#: Images de serveur Redis interdites dans la distribution.
_IMAGES_INTERDITES = re.compile(r"\bimage:\s*[\"']?redis[:/]", re.IGNORECASE)

VALKEY_TAG = "8.1.9-alpine"
VALKEY_DIGEST = "sha256:e0eb7c480958d32bdc4357a74bdd70653ae15f2f9b4c93c4a5a9fad1dc471c84"


def _lire(chemin: str) -> str:
    return (REPO_ROOT / chemin).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(_lire("docker-compose.yml"))


# ── le serveur Redis a disparu de la distribution ───────────────────────────


@pytest.mark.parametrize("chemin", _FICHIERS_DISTRIBUTION)
def test_no_redis_server_image_in_distribution_files(chemin):
    """Ni `redis:7.4`, ni `redis:latest`, ni aucune image serveur Redis."""
    for numero, ligne in enumerate(_lire(chemin).splitlines(), start=1):
        assert not _IMAGES_INTERDITES.search(ligne), (
            f"{chemin}:{numero} réintroduit une image serveur Redis — "
            "elle est écartée de la distribution (licence source-available)"
        )


@pytest.mark.parametrize("motif", ["redis:7.4", "redis:latest", "redis:7-alpine"])
def test_specific_forbidden_tags_are_absent(motif):
    for chemin in _FICHIERS_DISTRIBUTION:
        assert motif not in _lire(chemin), f"{chemin} contient encore {motif}"


def test_no_redis_service_remains(compose):
    assert "redis" not in compose["services"], "le service `redis` doit être remplacé"
    assert "valkey" in compose["services"]


def test_no_redis_volume_remains(compose):
    """Un volume `redis_data` réutilisé affirmerait une compatibilité non testée."""
    assert "redis_data" not in compose["volumes"]
    assert "valkey_data" in compose["volumes"]


# ── l'image Valkey est épinglée et qualifiée ────────────────────────────────


def test_valkey_image_is_pinned_by_tag_and_digest(compose):
    image = compose["services"]["valkey"]["image"]
    assert image.startswith(f"valkey/valkey:{VALKEY_TAG}@"), image
    assert image.endswith(VALKEY_DIGEST), "un tag est mutable, un digest non"


def test_valkey_service_is_healthchecked(compose):
    service = compose["services"]["valkey"]
    assert "valkey-cli" in " ".join(service["healthcheck"]["test"])
    assert "valkey-server" in service["command"]
    assert service["volumes"] == ["valkey_data:/data"]


def test_services_depend_on_valkey(compose):
    """Le renommage doit avoir suivi partout, sinon la stack ne démarre pas."""
    dependants = [
        nom for nom, svc in compose["services"].items() if "valkey" in (svc.get("depends_on") or {})
    ]
    assert dependants, "aucun service ne dépend de valkey"
    for nom, svc in compose["services"].items():
        assert "redis" not in (svc.get("depends_on") or {}), f"{nom} dépend encore de `redis`"


def test_the_url_still_uses_the_protocol_scheme(compose):
    """`redis://` est le nom du PROTOCOLE : le conserver évite un changement inutile."""
    url = compose["services"]["app"]["environment"]["REDIS_URL"]
    assert "redis://valkey:6379" in url, url


# ── la provenance est écrite, pas supposée ──────────────────────────────────


def test_image_provenance_is_documented():
    fiche = _lire("docs/governance/VALKEY_IMAGE_PROVENANCE.md")
    for element in (VALKEY_TAG, VALKEY_DIGEST, "BSD-3-Clause", "2026-08-28", "valkey-io/valkey"):
        assert element in fiche, f"provenance incomplète : {element} absent"


def test_the_license_text_is_versioned():
    texte = _lire("licenses/third-party/containers/valkey/COPYING")
    assert "SPDX-License-Identifier: BSD-3-Clause" in texte
    assert "Redistributions of source code" in texte
    provenance = _lire("licenses/third-party/containers/valkey/PROVENANCE.txt")
    assert "raw.githubusercontent.com/valkey-io/valkey/8.1.9/COPYING" in provenance


def test_the_client_library_licence_is_not_confused_with_the_server():
    """`redis-py` est le client, MIT ; le changement de 2024 vise le serveur."""
    fiche = _lire("docs/governance/VALKEY_IMAGE_PROVENANCE.md")
    assert "`redis-py` est le **client du protocole**" in fiche
    assert "MIT" in fiche


def test_the_runbook_documents_both_scenarios():
    runbook = _lire("docs/VALKEY_MIGRATION_RUNBOOK.md")
    assert "Scénario A" in runbook and "Scénario B" in runbook
    assert "volume neuf" in runbook
    assert "Aucune bascule automatique" in runbook


def test_the_runbook_states_the_denylist_consequence():
    """Repartir d'une denylist vide n'est pas neutre : le dire, pas le taire."""
    # Le texte est enveloppé sur plusieurs lignes de citation : on compare le
    # contenu, pas sa mise en page.
    runbook = " ".join(_lire("docs/VALKEY_MIGRATION_RUNBOOK.md").replace(">", " ").split())
    assert "redeviennent acceptés jusqu'à leur expiration naturelle" in runbook


# ── invariants cliniques préservés par la migration ─────────────────────────


def test_analyzer_interfaces_stay_disabled():
    config = _lire("app/core/config.py")
    for reglage in (
        "ENABLE_DH36_LISTENER: bool = False",
        "ANALYZER_RAW_LISTENER_ENABLED: bool = False",
        "CSA_SYNC_ENABLED: bool = False",
    ):
        assert reglage in config, f"réglage modifié par la migration : {reglage}"


def test_clinical_status_is_unchanged():
    assert _lire("docs/governance/CLINICAL_STATUS").strip() == "REAL_DATA_NO_GO"


def test_the_compatibility_version_pitfall_is_documented():
    """Valkey annonce `redis_version: 7.2.4` — un piège pour un code futur."""
    fiche = _lire("docs/governance/VALKEY_IMAGE_PROVENANCE.md")
    assert "redis_version: 7.2.4" in fiche
    assert "compatibilité protocolaire" in fiche


def test_no_code_branches_on_the_reported_redis_version():
    """Le constat ci-dessus n'a de valeur que s'il reste vrai."""
    sources = list((REPO_ROOT / "app").rglob("*.py"))
    fautifs = [p for p in sources if "redis_version" in p.read_text(encoding="utf-8")]
    assert not fautifs, f"un comportement dépend de redis_version : {fautifs}"

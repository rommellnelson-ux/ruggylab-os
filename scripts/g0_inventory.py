"""Inventaire G0 — architecture, surfaces d'entrée et données.

Une baseline n'a de valeur que si elle est **régénérable**. Un inventaire tenu à
la main dérive dès la première modification du code, sans que personne s'en
aperçoive : c'est pourquoi tout ce que ce script produit est dérivé du dépôt ou
du runtime, jamais recopié.

Trois inventaires sont produits :

``inventory.json``
    modules, points d'entrée, services Compose et leur classement — cœur,
    optionnel, développement ou override.

``entrypoints.json``
    **toutes** les surfaces d'entrée, HTTP et non HTTP. OpenAPI décrit le
    contrat documenté ; il ignore les routes hors schéma, les WebSockets, les
    montages, le scheduler, les listeners et les scripts. S'y limiter donnerait
    une fausse impression de complétude.

``routes.json``
    le contrat HTTP tel que l'application le génère réellement, croisé avec
    l'arbre de routage runtime.

Le schéma PostgreSQL et le graphe Alembic sont produits par
``scripts/g0_schema_inventory.py``, qui exige une base réellement migrée.

**Déterminisme.** Le corps de chaque artefact (``payload``) est trié et stable :
deux générations sur le même commit produisent des octets identiques. Les
champs volatils — l'heure notamment — vivent dans ``provenance.json``, à part.
Les laisser dans le corps comparé par ``--check`` produirait un diff permanent :
le contrôle échouerait toujours, on l'ignorerait, et il ne servirait plus à rien.

Aucun appel réseau. Aucun secret. Aucune donnée patient.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Structure des artefacts. À incrémenter dès que la forme change, sans quoi
#: deux inventaires de structures différentes seraient indiscernables.
SCHEMA_VERSION = "1.0.0"

#: Version du générateur. Un changement de résultat s'explique d'abord par là.
GENERATOR_VERSION = "1.0.0"

RACINE = Path(__file__).resolve().parents[1]

#: Fichiers Compose et ce qu'ils représentent. Le classement n'est pas
#: cosmétique : il dit ce qui est distribué et ce qui ne l'est pas.
_COMPOSE = {
    "docker-compose.yml": ("core", "Stack de production — mode nominal supporté"),
    "docker-compose.dev.yml": ("dev_override", "Surcharge de développement"),
    "docker-compose.monitoring.yml": ("optional_overlay", "Supervision Grafana, hors du cœur"),
    "docker-compose.monitoring.dev.yml": ("dev_override", "Port loopback pour l'overlay"),
    "docker-compose.analyzers.yml": ("optional_overlay", "Interfaces automates — désactivées"),
}

#: Réglages dont l'état par défaut engage la sécurité ou la gouvernance.
_REGLAGES_SURVEILLES = (
    "CSA_SYNC_ENABLED",
    "ENABLE_DH36_LISTENER",
    "ANALYZER_RAW_LISTENER_ENABLED",
    "REQUIRE_VALIDATION_FOR_RELEASE",
    "CACHE_BACKEND",
    "ANALYZER_BIND_IP",
)


# ── provenance ──────────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    resultat = subprocess.run(
        ["git", *args], cwd=RACINE, capture_output=True, text=True, encoding="utf-8"
    )
    return resultat.stdout.strip() if resultat.returncode == 0 else "inconnu"


def provenance(commande: str) -> dict[str, Any]:
    """Ce qui situe l'inventaire, et que `--check` ne compare pas.

    Sans ces champs, un artefact ne dit pas de quel code il parle. Avec eux
    dans le corps, `--check` échouerait à chaque exécution.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_git_sha": _git("rev-parse", "HEAD"),
        "source_git_ref": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "generation_command": commande,
        "platform": f"{platform.system().lower()}/{platform.machine().lower()}",
        "python_version": platform.python_version(),
        "_comment": (
            "Champs volatils, deliberement separes du payload : les inclure dans "
            "la comparaison de --check produirait un diff permanent."
        ),
    }


# ── inventaire du code ──────────────────────────────────────────────────────


def _modules_python() -> list[dict[str, Any]]:
    """Modules de `app/`, avec leur taille. Comptés, jamais estimés."""
    modules = []
    for chemin in sorted((RACINE / "app").rglob("*.py")):
        relatif = chemin.relative_to(RACINE).as_posix()
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        modules.append(
            {
                "path": relatif,
                "package": chemin.parent.relative_to(RACINE).as_posix(),
                "lines": len(texte.splitlines()),
            }
        )
    return modules


def _points_entree_processus() -> list[dict[str, Any]]:
    """Processus que l'application sait démarrer, et leur rôle."""
    entrees = [
        {
            "name": "web",
            "type": "process",
            "command": "uvicorn app.main:app",
            "module": "app/main.py",
            "role": "API, interface, WebSocket",
            "default_state": "enabled",
        },
        {
            "name": "scheduler",
            "type": "process",
            "command": "python -m app.scheduler",
            "module": "app/scheduler.py",
            "role": "tâches périodiques, purge des jetons",
            "default_state": "enabled",
        },
        {
            "name": "analyzer-gateway",
            "type": "process",
            "command": "python -m app.analyzer_gateway",
            "module": "app/analyzer_gateway.py",
            "role": "hôte des interfaces d'équipement",
            "default_state": "enabled_but_all_interfaces_disabled",
        },
        {
            "name": "migrate",
            "type": "one_shot",
            "command": "alembic upgrade head",
            "module": "alembic/",
            "role": "application des migrations",
            "default_state": "manual",
        },
    ]
    return [e for e in entrees if (RACINE / e["module"].rstrip("/")).exists()]


def _scripts_cli() -> list[dict[str, Any]]:
    """Scripts exécutables du dépôt. Chacun est une porte d'entrée."""
    scripts = []
    for chemin in sorted((RACINE / "scripts").glob("*.py")):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        scripts.append(
            {
                "path": chemin.relative_to(RACINE).as_posix(),
                "type": "cli_script",
                "has_main_guard": "__main__" in texte,
                "docstring_first_line": (ast.get_docstring(ast.parse(texte)) or "").split("\n")[0],
            }
        )
    for chemin in sorted((RACINE / "scripts").glob("*.sh")):
        scripts.append(
            {
                "path": chemin.relative_to(RACINE).as_posix(),
                "type": "shell_script",
                "has_main_guard": None,
                "docstring_first_line": "",
            }
        )
    return scripts


def _reglages_par_defaut() -> list[dict[str, Any]]:
    """État par défaut des réglages qui engagent la sécurité ou la gouvernance."""
    config = (RACINE / "app" / "core" / "config.py").read_text(encoding="utf-8")
    releves = []
    for ligne in config.splitlines():
        depouille = ligne.strip()
        for reglage in _REGLAGES_SURVEILLES:
            if depouille.startswith(f"{reglage}:") or depouille.startswith(f"{reglage} ="):
                valeur = depouille.split("=", 1)[1].strip() if "=" in depouille else ""
                releves.append({"setting": reglage, "default": valeur.split("#")[0].strip()})
                break
    return sorted(releves, key=lambda r: r["setting"])


# ── inventaire Compose ──────────────────────────────────────────────────────


def _compose() -> list[dict[str, Any]]:
    """Services de chaque fichier Compose, avec leur classement.

    Le classement dit ce qui est distribué. Un service rangé « cœur » alors
    qu'il est optionnel ferait croire à une obligation qui n'existe pas — et
    l'inverse masquerait une obligation réelle.
    """
    import yaml

    fichiers = []
    for nom, (statut, role) in sorted(_COMPOSE.items()):
        chemin = RACINE / nom
        if not chemin.is_file():
            continue
        contenu = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        services = []
        for service, definition in sorted((contenu.get("services") or {}).items()):
            image = definition.get("image", "")
            tag, digest = "", ""
            if image:
                sans_digest, _, digest = image.partition("@")
                _, _, tag = sans_digest.rpartition(":")
            depends = definition.get("depends_on") or {}
            services.append(
                {
                    "service": service,
                    "image": image or "(construite depuis le Dockerfile)",
                    "tag": tag,
                    "digest": digest,
                    "command": definition.get("command", ""),
                    "networks": sorted(definition.get("networks") or []),
                    "volumes": sorted(str(v) for v in (definition.get("volumes") or [])),
                    "published_ports": sorted(str(p) for p in (definition.get("ports") or [])),
                    "has_healthcheck": "healthcheck" in definition,
                    "depends_on": sorted(depends) if isinstance(depends, dict) else sorted(depends),
                    "profiles": sorted(definition.get("profiles") or []),
                    "required_variables": sorted(
                        _variables_requises(json.dumps(definition, ensure_ascii=False))
                    ),
                }
            )
        fichiers.append(
            {
                "file": nom,
                "status": statut,
                "role": role,
                "services": services,
                "volumes": sorted(contenu.get("volumes") or {}),
                "networks": sorted(contenu.get("networks") or {}),
            }
        )
    return fichiers


def _variables_requises(texte: str) -> set[str]:
    """Variables d'environnement sans valeur par défaut : elles sont obligatoires."""
    import re

    requises = set()
    for correspondance in re.finditer(r"\$\{([A-Z_][A-Z0-9_]*)(:?[-?])?", texte):
        nom, operateur = correspondance.group(1), correspondance.group(2)
        if operateur in (None, ":?", "?"):
            requises.add(nom)
    return requises


# ── surfaces d'entrée ───────────────────────────────────────────────────────


def _charger_application():
    """Importe l'application avec une configuration SYNTHÉTIQUE.

    Aucun secret de production, aucune base réelle : l'inventaire décrit des
    surfaces, pas des données.
    """
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("SECRET_KEY", "g0-inventory-synthetic-key-not-a-secret-32")
    os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "G0Synthetic!Password1")
    os.environ.setdefault("DATABASE_URL", "sqlite:///./g0_inventory.db")
    os.environ.setdefault("CACHE_BACKEND", "memory")

    # Le script est lançable depuis n'importe quel répertoire : la racine du
    # dépôt doit être sur le chemin d'import, sinon `app` reste introuvable.
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    from app.main import app

    return app


#: Chemins que le proxy renvoie en 404 aux utilisateurs (vérifié en CI par le
#: job `docker-stack`). Ils existent, mais ne sont pas joignables de l'extérieur.
_BLOQUES_AU_PROXY = ("/metrics", "/docs", "/redoc", "/openapi.json")

#: Dépendances qui prouvent qu'une route exige un porteur de jeton.
_MARQUEURS_AUTH = ("OAuth2PasswordBearer", "HTTPBearer", "APIKeyHeader")

#: Dépendances qui restreignent au-delà de la simple authentification.
_MARQUEURS_ROLE = ("superuser", "admin", "require_role", "require_permission")


def _dependances_de_route(route) -> list[str]:
    """Noms des dépendances réellement appliquées à une route.

    C'est la seule source fiable : le champ `securitySchemes` de l'OpenAPI est
    global, et laisserait croire que toutes les routes sont protégées — y
    compris celles qui ne le sont pas.
    """
    from fastapi.dependencies.utils import get_flat_dependant

    noms = set()
    for dependance in get_flat_dependant(route.dependant, skip_repeats=True).dependencies:
        appelable = getattr(dependance, "call", None)
        if appelable is None:
            continue
        noms.add(getattr(appelable, "__name__", type(appelable).__name__))
    return sorted(noms)


def _classer_route(chemin: str, dependances: list[str], tags: list[str]) -> str:
    """Classement d'exposition, dérivé des dépendances — pas d'un drapeau global.

    `A_QUALIFIER` est délibérément conservé : une route dont on ne sait pas dire
    si elle est protégée doit être examinée, pas rangée par défaut du côté
    rassurant.
    """
    if chemin in _BLOQUES_AU_PROXY:
        return "BLOCKED_AT_PROXY"
    if chemin.startswith("/health"):
        return "INTERNAL"

    aplati = " ".join(dependances).lower()
    authentifiee = any(marqueur in dependances for marqueur in _MARQUEURS_AUTH)
    if authentifiee and any(marqueur in aplati for marqueur in _MARQUEURS_ROLE):
        return "ADMIN_ONLY"
    if authentifiee:
        return "AUTHENTICATED"
    if "admin" in chemin.lower() or "admin" in [t.lower() for t in tags]:
        # Nommée « admin » sans garde détectée : c'est exactement le cas qu'il
        # faut faire remonter, pas classer.
        return "A_QUALIFIER"
    if chemin == "/" or chemin.startswith("/app"):
        return "PUBLIC"
    return "A_QUALIFIER"


def _surfaces_http(app) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Contrat OpenAPI et arbre de routage runtime, croisés.

    Les deux sources sont nécessaires : l'OpenAPI ignore les routes hors
    schéma, les WebSockets et les montages ; l'arbre runtime ignore les
    schémas d'entrée et de sortie.
    """
    from fastapi.routing import APIRoute
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles

    openapi = app.openapi()

    # Dépendances réelles, indexées par (chemin, méthode).
    dependances_par_operation: dict[tuple[str, str], list[str]] = {}
    modules_par_operation: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            noms = _dependances_de_route(route)
            module = getattr(route.endpoint, "__module__", "")
            for methode in route.methods or []:
                dependances_par_operation[(route.path, methode)] = noms
                modules_par_operation[(route.path, methode)] = module

    routes_openapi: list[dict[str, Any]] = []
    for chemin, operations in sorted(openapi.get("paths", {}).items()):
        for methode, definition in sorted(operations.items()):
            if methode.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            cle = (chemin, methode.upper())
            dependances = dependances_par_operation.get(cle, [])
            tags = sorted(definition.get("tags") or [])
            routes_openapi.append(
                {
                    "path": chemin,
                    "method": methode.upper(),
                    "operation_id": definition.get("operationId", ""),
                    "tags": tags,
                    "source_module": modules_par_operation.get(cle, ""),
                    "has_request_schema": "requestBody" in definition,
                    "response_codes": sorted(definition.get("responses", {})),
                    "security_dependencies": dependances,
                    "authenticated": any(m in dependances for m in _MARQUEURS_AUTH),
                    "exposure": _classer_route(chemin, dependances, tags),
                }
            )

    chemins_documentes = {(r["path"], r["method"]) for r in routes_openapi}
    runtime: list[dict[str, Any]] = []
    for route in app.routes:
        entree: dict[str, Any] = {
            "path": getattr(route, "path", ""),
            "name": getattr(route, "name", ""),
        }
        if isinstance(route, APIRoute):
            entree["kind"] = "APIRoute"
            entree["methods"] = sorted(route.methods or [])
            entree["in_openapi"] = route.include_in_schema
            entree["undocumented"] = any(
                (route.path, m) not in chemins_documentes for m in (route.methods or [])
            )
        elif isinstance(route, WebSocketRoute):
            entree["kind"] = "WebSocketRoute"
            entree["methods"] = ["WEBSOCKET"]
            entree["in_openapi"] = False
            entree["undocumented"] = True
        elif isinstance(route, Mount):
            entree["kind"] = "StaticFiles" if isinstance(route.app, StaticFiles) else "Mount"
            entree["methods"] = []
            entree["in_openapi"] = False
            entree["undocumented"] = True
        elif isinstance(route, Route):
            entree["kind"] = "Route"
            entree["methods"] = sorted(route.methods or [])
            entree["in_openapi"] = getattr(route, "include_in_schema", False)
            entree["undocumented"] = not getattr(route, "include_in_schema", False)
        else:
            entree["kind"] = type(route).__name__
            entree["methods"] = []
            entree["in_openapi"] = False
            entree["undocumented"] = True
        runtime.append(entree)

    runtime.sort(key=lambda r: (r["path"], r["kind"], str(r.get("methods"))))
    return routes_openapi, runtime


def _surfaces_non_http() -> list[dict[str, Any]]:
    """Portes d'entrée qui ne passent pas par HTTP.

    Les omettre laisserait croire que le système ne s'atteint que par l'API.
    """
    return [
        {
            "name": "scheduler",
            "type": "background_process",
            "trigger": "périodique (intervalle interne)",
            "default_state": "enabled",
            "network_exposure": "aucune",
            "guard": "process unique, heartbeat",
            "handles": "jetons expirés, tâches de maintenance",
        },
        {
            "name": "analyzer-gateway",
            "type": "background_process",
            "trigger": "démarrage du conteneur",
            "default_state": "enabled_with_all_interfaces_disabled",
            "network_exposure": "aucun port publié par la stack de base",
            "guard": "ENABLE_DH36_LISTENER=false, ANALYZER_RAW_LISTENER_ENABLED=false",
            "handles": "trames d'équipement — aucune par défaut",
        },
        {
            "name": "listener DH36",
            "type": "tcp_listener",
            "trigger": "ENABLE_DH36_LISTENER=true",
            "default_state": "disabled",
            "network_exposure": "ANALYZER_BIND_IP, jamais 0.0.0.0 (refus au démarrage)",
            "guard": "désactivé par défaut",
            "handles": "trames analyseur d'hématologie",
        },
        {
            "name": "listener trames brutes",
            "type": "tcp_listener",
            "trigger": "ANALYZER_RAW_LISTENER_ENABLED=true",
            "default_state": "disabled",
            "network_exposure": "ANALYZER_BIND_IP",
            "guard": "désactivé par défaut ; file bornée par LTRIM",
            "handles": "trames brutes archivées",
        },
        {
            "name": "migrations Alembic",
            "type": "one_shot_job",
            "trigger": "profil `migrate`, manuel",
            "default_state": "manual",
            "network_exposure": "aucune",
            "guard": "verrou de migration au démarrage de l'application",
            "handles": "schéma de la base",
        },
        {
            "name": "sauvegarde PostgreSQL",
            "type": "scheduled_job",
            "trigger": "service `db-backup`",
            "default_state": "enabled",
            "network_exposure": "aucune",
            "guard": "dump vérifié par somme SHA-256",
            "handles": "copie complète de la base",
        },
        {
            "name": "collecte Prometheus",
            "type": "scrape_target",
            "trigger": "Prometheus interroge /metrics",
            "default_state": "enabled",
            "network_exposure": "réseau interne uniquement ; /metrics bloqué au proxy",
            "guard": "non exposé publiquement",
            "handles": "métriques techniques, aucune donnée patient",
        },
    ]


# ── assemblage ──────────────────────────────────────────────────────────────


def construire(app) -> dict[str, dict[str, Any]]:
    """Les trois inventaires, sous une forme triée et stable."""
    routes_openapi, runtime = _surfaces_http(app)
    non_http = _surfaces_non_http()
    modules = _modules_python()
    compose = _compose()

    inventaire = {
        "application": {
            "module_count": len(modules),
            "total_lines": sum(m["lines"] for m in modules),
            "packages": sorted({m["package"] for m in modules}),
            "modules": modules,
            "process_entrypoints": _points_entree_processus(),
            "cli_scripts": _scripts_cli(),
            "governance_defaults": _reglages_par_defaut(),
        },
        "compose": compose,
        "expected_processes": sorted(
            {
                service["service"]
                for fichier in compose
                if fichier["status"] == "core"
                for service in fichier["services"]
            }
        ),
    }

    entrypoints = {
        "http": {
            "openapi_operations": len(routes_openapi),
            "runtime_routes": len(runtime),
            "undocumented_runtime_routes": sum(1 for r in runtime if r["undocumented"]),
            "websockets": sum(1 for r in runtime if r["kind"] == "WebSocketRoute"),
            "mounts": sum(1 for r in runtime if r["kind"] in ("Mount", "StaticFiles")),
            "routes": runtime,
        },
        "non_http": non_http,
        "totals": {
            "http_surfaces": len(runtime),
            "non_http_surfaces": len(non_http),
            "all_surfaces": len(runtime) + len(non_http),
        },
    }

    routes = {
        "openapi_paths": len({r["path"] for r in routes_openapi}),
        "openapi_operations": len(routes_openapi),
        "by_exposure": {
            classe: sum(1 for r in routes_openapi if r["exposure"] == classe)
            for classe in sorted({r["exposure"] for r in routes_openapi})
        },
        "operations": routes_openapi,
    }

    return {"inventory": inventaire, "entrypoints": entrypoints, "routes": routes}


def _ecrire(chemin: Path, payload: Any) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "payload": payload},
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _lire_payload(chemin: Path) -> Any:
    if not chemin.is_file():
        return None
    return json.loads(chemin.read_text(encoding="utf-8")).get("payload")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", help="écrit les artefacts")
    parser.add_argument(
        "--check",
        action="store_true",
        help="échoue si les artefacts versionnés divergent de ce qui est régénéré",
    )
    parser.add_argument("--output-dir", type=Path, default=RACINE / "artifacts" / "g0")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    if not (args.generate or args.check or args.print_summary):
        parser.error("choisir --generate, --check ou --print-summary")

    app = _charger_application()
    artefacts = construire(app)

    if args.print_summary:
        inv, ent, rte = artefacts["inventory"], artefacts["entrypoints"], artefacts["routes"]
        print(f"Modules Python                 : {inv['application']['module_count']}")
        print(f"Lignes (app/)                  : {inv['application']['total_lines']}")
        print(f"Scripts CLI                    : {len(inv['application']['cli_scripts'])}")
        print(f"Fichiers Compose               : {len(inv['compose'])}")
        print(f"Services du cœur               : {len(inv['expected_processes'])}")
        print(f"Chemins OpenAPI                : {rte['openapi_paths']}")
        print(f"Opérations OpenAPI             : {rte['openapi_operations']}")
        print(f"Routes runtime                 : {ent['http']['runtime_routes']}")
        print(f"  dont hors OpenAPI            : {ent['http']['undocumented_runtime_routes']}")
        print(f"  dont WebSockets              : {ent['http']['websockets']}")
        print(f"  dont montages / statiques    : {ent['http']['mounts']}")
        print(f"Surfaces non HTTP              : {ent['totals']['non_http_surfaces']}")
        print(f"TOTAL des surfaces d'entrée    : {ent['totals']['all_surfaces']}")
        print("\nExposition des opérations HTTP :")
        for classe, total in sorted(rte["by_exposure"].items()):
            print(f"  {classe:20s} {total}")

    if args.generate:
        for nom, payload in artefacts.items():
            _ecrire(args.output_dir / f"{nom}.json", payload)
        (args.output_dir / "provenance.json").write_text(
            json.dumps(
                provenance("python scripts/g0_inventory.py --generate"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nArtefacts écrits dans {args.output_dir}")

    if args.check:
        divergences = []
        for nom, payload in artefacts.items():
            versionne = _lire_payload(args.output_dir / f"{nom}.json")
            if versionne is None:
                divergences.append(f"{nom}.json absent")
            elif versionne != payload:
                divergences.append(f"{nom}.json diverge du code")
        if divergences:
            print("\nECHEC : les artefacts versionnés ne décrivent plus le code.", file=sys.stderr)
            for message in divergences:
                print(f"  ! {message}", file=sys.stderr)
            print(
                "\nRégénérer avec : python scripts/g0_inventory.py --generate",
                file=sys.stderr,
            )
            return 1
        print("\nLes artefacts versionnés correspondent au code.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

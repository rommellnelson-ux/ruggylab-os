"""Tests — la baseline G0 décrit le code, et le dit encore demain.

Un inventaire versionné qui n'est pas comparé au code dérive à la première
modification, sans que personne s'en aperçoive : il devient alors pire qu'une
absence d'inventaire, parce qu'on lui fait confiance.

Ces tests portent sur les preuves du **lot A** : inventaire, C4, surfaces
d'entrée, schéma. Ils ne jugent pas la qualité de l'architecture — ils
vérifient que la photographie est fidèle et le reste.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTEFACTS = REPO_ROOT / "artifacts" / "g0"
DOCS = REPO_ROOT / "docs" / "g0"


def _payload(nom: str):
    chemin = ARTEFACTS / f"{nom}.json"
    assert chemin.is_file(), f"artefact G0 absent : {chemin}"
    return json.loads(chemin.read_text(encoding="utf-8"))["payload"]


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _aplati(chemin: Path) -> str:
    """Le texte d'un document, débarrassé de sa mise en forme Markdown.

    Une phrase coupée par un retour à la ligne ou préfixée d'un chevron de
    citation ne doit pas faire échouer un test qui cherche cette phrase : ce
    serait faire dépendre une preuve de la largeur de ses lignes.
    """
    lignes = [re.sub(r"^\s*>\s?", "", ligne) for ligne in _lire(chemin).splitlines()]
    return " ".join(" ".join(lignes).replace("*", "").replace("`", "").split())


@pytest.fixture(scope="module")
def inventaire():
    return _payload("inventory")


@pytest.fixture(scope="module")
def surfaces():
    return _payload("entrypoints")


@pytest.fixture(scope="module")
def routes():
    return _payload("routes")


@pytest.fixture(scope="module")
def compose_coeur():
    return yaml.safe_load(_lire(REPO_ROOT / "docker-compose.yml"))


# ── déterminisme : sans lui, `--check` ne prouve rien ───────────────────────


def test_two_generations_produce_the_same_payload():
    """Un payload instable rendrait `--check` inutilisable.

    S'il différait à chaque exécution, le contrôle échouerait toujours, on
    l'ignorerait, et la baseline dériverait sans obstacle.
    """
    from scripts.g0_inventory import _charger_application, construire

    app = _charger_application()
    premier = json.dumps(construire(app), sort_keys=True)
    second = json.dumps(construire(app), sort_keys=True)
    assert premier == second, "deux générations successives divergent"


def test_volatile_fields_live_outside_the_compared_payload():
    """L'heure de génération ne doit pas provoquer un diff permanent."""
    from scripts.g0_inventory import provenance

    entete = provenance("test")
    assert "generated_at" in entete["volatile"]
    assert "generated_at" not in entete["deterministic"]
    for nom in ("inventory", "entrypoints", "routes"):
        corps = json.dumps(_payload(nom))
        assert "generated_at" not in corps, f"{nom}.json porte un champ volatil"


def test_check_detects_a_divergence(tmp_path):
    """Un contrôle qui ne détecte rien ne protège de rien."""
    from scripts.g0_inventory import main

    for nom in ("inventory", "entrypoints", "routes"):
        source = json.loads(_lire(ARTEFACTS / f"{nom}.json"))
        if nom == "routes":
            source["payload"]["operations"] = source["payload"]["operations"][:-1]
        (tmp_path / f"{nom}.json").write_text(json.dumps(source), encoding="utf-8")
    assert main(["--check", "--output-dir", str(tmp_path)]) == 1


def test_check_passes_on_the_versioned_artifacts():
    from scripts.g0_inventory import main

    assert main(["--check", "--output-dir", str(ARTEFACTS)]) == 0


# ── surfaces d'entrée : rien ne doit manquer ────────────────────────────────


def test_every_openapi_operation_is_inventoried(routes):
    from scripts.g0_inventory import _charger_application

    app = _charger_application()
    attendues = {
        (chemin, methode.upper())
        for chemin, operations in app.openapi()["paths"].items()
        for methode in operations
        if methode.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE")
    }
    recensees = {(o["path"], o["method"]) for o in routes["operations"]}
    assert recensees == attendues, f"écart : {attendues ^ recensees}"


def test_every_runtime_route_is_inventoried(surfaces):
    from scripts.g0_inventory import _charger_application

    app = _charger_application()
    assert surfaces["http"]["runtime_routes"] == len(app.routes)


def test_websockets_and_mounts_are_not_omitted(surfaces):
    """L'OpenAPI les ignore : les omettre laisserait des portes hors inventaire."""
    types = {r["kind"] for r in surfaces["http"]["routes"]}
    assert "WebSocketRoute" in types, "aucun WebSocket recensé"
    assert types & {"Mount", "StaticFiles"}, "aucun montage recensé"
    assert surfaces["http"]["undocumented_runtime_routes"] > 0


def test_non_http_surfaces_are_inventoried(surfaces):
    noms = {s["name"] for s in surfaces["non_http"]}
    for attendu in ("scheduler", "analyzer-gateway", "migrations Alembic"):
        assert attendu in noms, f"surface non HTTP absente : {attendu}"
    for surface in surfaces["non_http"]:
        for champ in ("type", "trigger", "default_state", "network_exposure", "guard"):
            assert surface.get(champ), f"{surface['name']} : champ {champ} vide"


def test_the_total_counts_every_surface(surfaces):
    totaux = surfaces["totals"]
    assert totaux["all_surfaces"] == totaux["http_surfaces"] + totaux["non_http_surfaces"]


# ── exposition : dérivée du code, et qualifiée par écrit ────────────────────


def test_exposure_is_derived_from_real_dependencies(routes):
    """Le champ `securitySchemes` est global : s'y fier classerait tout comme
    authentifié, y compris ce qui ne l'est pas."""
    classes = set(routes["by_exposure"])
    assert len(classes) > 1, "classement non discriminant"
    assert any(o["security_dependencies"] for o in routes["operations"])


def test_every_unauthenticated_route_is_qualified_in_writing(routes):
    """Une route non authentifiée sans justification écrite est un défaut."""
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    qualifiees = {entree["path"] for entree in registre["qualified_routes"]}
    a_qualifier = {
        o["path"] for o in routes["operations"] if o["exposure"] in ("PUBLIC", "A_QUALIFIER")
    }
    manquantes = a_qualifier - qualifiees
    assert not manquantes, f"routes non qualifiées : {sorted(manquantes)}"


@pytest.mark.parametrize("champ", ["constat", "justification", "risque_residuel"])
def test_every_qualification_is_argued(champ):
    """Une case cochée sans phrase ne vaut pas une qualification.

    Un renvoi vers une autre route du registre reste recevable — à condition
    que la route citée y soit elle-même qualifiée, sinon le renvoi ne mène
    nulle part.
    """
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    qualifiees = {entree["path"] for entree in registre["qualified_routes"]}
    for entree in registre["qualified_routes"]:
        valeur = entree.get(champ, "")
        if len(valeur) > 20:
            continue
        trouve = re.search(r"(/[\w./{}-]*)", valeur)
        renvoi = trouve.group(1).rstrip(".") if trouve else None
        assert renvoi in qualifiees, (
            f"{entree['path']} : champ {champ} ni argumenté ni renvoyé — {valeur!r}"
        )


def test_every_qualification_carries_a_severity():
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    for entree in registre["qualified_routes"]:
        assert entree.get("classement") in ("P0", "P1", "P2"), entree["path"]


def test_the_register_qualifies_and_does_not_correct():
    aplati = " ".join(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json").split())
    assert "Ce registre QUALIFIE ; il ne corrige rien" in aplati.replace("\\", "")


# ── Compose : tout est classé, et le C4 lui correspond ──────────────────────

_STATUTS_VALIDES = {"core", "dev_override", "optional_overlay"}


def test_every_compose_file_is_classified(inventaire):
    fichiers = {f["file"] for f in inventaire["compose"]}
    for attendu in (
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.monitoring.yml",
        "docker-compose.monitoring.dev.yml",
        "docker-compose.analyzers.yml",
    ):
        assert attendu in fichiers, f"fichier Compose non inventorié : {attendu}"
    for fichier in inventaire["compose"]:
        assert fichier["status"] in _STATUTS_VALIDES, fichier


def test_every_compose_service_carries_its_details(inventaire):
    for fichier in inventaire["compose"]:
        for service in fichier["services"]:
            for champ in (
                "service",
                "image_reference_kind",
                "image_template",
                "resolved_image",
                "registry",
                "repository",
                "tag",
                "digest",
                "required_variable",
                "runtime_kind",
                "started_by_default",
                "networks",
                "volumes",
                "published_ports",
            ):
                assert champ in service, f"{fichier['file']}/{service.get('service')} : {champ}"


def _diagramme_conteneurs() -> str:
    """Le bloc Mermaid de la section « C4 — Conteneurs », et lui seul.

    Chercher dans tout le document laisserait passer un service retiré du
    diagramme mais encore cité dans une phrase voisine.
    """
    sections = _lire(DOCS / "C4.md").split("## 2. C4 — Conteneurs", 1)
    assert len(sections) == 2, "section « C4 — Conteneurs » introuvable"
    bloc = re.search(r"```mermaid(.*?)```", sections[1], re.DOTALL)
    assert bloc, "aucun diagramme Mermaid dans la section Conteneurs"
    return bloc.group(1)


def _sous_graphe(diagramme: str, nom: str) -> str:
    """Les lignes d'un `subgraph` Mermaid, sans ce qui l'entoure."""
    lignes = diagramme.splitlines()
    debuts = [
        index for index, ligne in enumerate(lignes) if ligne.strip().startswith(f"subgraph {nom}")
    ]
    assert debuts, f"sous-graphe {nom} introuvable"
    depart = debuts[0]
    profondeur = 0
    for index in range(depart, len(lignes)):
        nu = lignes[index].strip()
        if nu.startswith("subgraph"):
            profondeur += 1
        elif nu == "end":
            profondeur -= 1
            if profondeur == 0:
                return "\n".join(lignes[depart + 1 : index])
    raise AssertionError(f"sous-graphe {nom} non refermé")


def test_the_core_services_match_the_c4_container_diagram(inventaire, compose_coeur):
    """Un diagramme qui montre autre chose que la réalité donne confiance à tort."""
    coeur = _sous_graphe(_diagramme_conteneurs(), "CORE")
    for service in sorted(compose_coeur["services"]):
        assert re.search(rf"\b{re.escape(service)}\b", coeur), (
            f"service `{service}` du cœur absent du sous-graphe CORE du C4"
        )
    for service in inventaire["core_services"]["service_definitions"]:
        assert service in compose_coeur["services"], (
            f"`{service}` figure dans l'inventaire mais plus dans le Compose"
        )


def test_no_grafana_in_the_core(inventaire, compose_coeur):
    assert "grafana" not in compose_coeur["services"]
    assert "grafana" not in _sous_graphe(_diagramme_conteneurs(), "CORE").lower(), (
        "Grafana est dessiné à l'intérieur du cœur : l'overlay serait présenté "
        "comme un composant distribué"
    )
    coeur = [f for f in inventaire["compose"] if f["status"] == "core"]
    for fichier in coeur:
        assert all("grafana" not in s["service"] for s in fichier["services"])
        assert all("GRAFANA" not in v for s in fichier["services"] for v in s["required_variables"])


def test_no_redis_server_and_valkey_present(inventaire, compose_coeur):
    assert "redis" not in compose_coeur["services"]
    assert "valkey" in compose_coeur["services"]
    coeur = [f for f in inventaire["compose"] if f["status"] == "core"][0]
    valkey = next(s for s in coeur["services"] if s["service"] == "valkey")
    assert valkey["image_reference_kind"] == "static"
    assert valkey["resolved_image"].startswith("valkey/valkey:")
    assert valkey["digest"], "l'image Valkey doit être épinglée par digest"


# ── C4 : chaque élément porte un statut réel ────────────────────────────────

_STATUTS_C4 = ("AS_BUILT", "PLANNED", "OPTIONAL", "DISABLED_BY_DEFAULT")


@pytest.mark.parametrize("statut", _STATUTS_C4)
def test_the_c4_uses_the_four_statuses(statut):
    assert statut in _lire(DOCS / "C4.md"), f"statut jamais employé : {statut}"


def test_the_deployment_view_does_not_claim_to_be_installed():
    """Présenter une architecture souhaitée comme installée est la faute la plus coûteuse."""
    aplati = _aplati(DOCS / "DEPLOYMENT_CSA_GR_PLATEAU.md")
    assert "rien n'est installé sur le site" in aplati
    assert "AS_BUILT en CI » n'est pas « installé sur le site »" in aplati


def test_the_deployment_view_covers_every_required_element():
    contenu = _lire(DOCS / "DEPLOYMENT_CSA_GR_PLATEAU.md")
    for element in (
        "Serveur ou poste hôte",
        "Postes utilisateurs",
        "Imprimante",
        "Réseau local",
        "Cible de copie hors machine",
        "papier",
        "Automates",
    ):
        assert element in contenu, f"élément absent de la vue de déploiement : {element}"


def test_the_diagrams_are_versioned_as_text():
    """Un diagramme binaire ne se relit pas dans une revue."""
    for document in ("C4.md", "DEPLOYMENT_CSA_GR_PLATEAU.md"):
        assert "```mermaid" in _lire(DOCS / document), f"{document} sans diagramme Mermaid"


# ── schéma PostgreSQL ───────────────────────────────────────────────────────


def test_the_schema_artifact_covers_every_object_category():
    schema = _payload("schema")
    for categorie in (
        "schemas",
        "tables",
        "columns",
        "primary_keys",
        "foreign_keys",
        "unique_constraints",
        "check_constraints",
        "indexes",
        "views",
        "sequences",
        "enums",
        "functions",
        "triggers",
        "extensions",
        "rls_policies",
        "table_privileges",
    ):
        assert categorie in schema, f"catégorie d'objet non interrogée : {categorie}"


def test_the_schema_comes_from_a_migrated_database():
    """Décrire les modèles reviendrait à décrire ce qu'on croit avoir."""
    schema = _payload("schema")
    tables = {t["table_name"] for t in schema["tables"]}
    assert "alembic_version" in tables, "la base introspectée n'a pas reçu `alembic upgrade head`"
    assert len(tables) >= 40


def test_every_table_has_a_primary_key():
    schema = _payload("schema")
    avec_pk = {p["table_name"] for p in schema["primary_keys"]}
    sans_pk = {t["table_name"] for t in schema["tables"]} - avec_pk
    assert not sans_pk, f"tables sans clé primaire : {sorted(sans_pk)}"


def test_alembic_has_a_single_head():
    """Deux têtes rendraient `upgrade head` ambigu, sans que rien ne le signale."""
    alembic = _payload("alembic-graph")
    assert alembic["single_head"], f"{alembic['head_count']} têtes : {alembic['heads']}"
    assert alembic["heads"] == ["20260826_0043"]
    assert alembic["head_matches_expected"]


def test_the_alembic_graph_records_branches_and_merges():
    alembic = _payload("alembic-graph")
    for champ in ("revisions", "topological_order", "merge_points", "branch_points"):
        assert champ in alembic
    assert len(alembic["topological_order"]) == alembic["revision_count"]


# ── ni donnée réelle, ni secret dans les artefacts ──────────────────────────

_MOTIFS_INTERDITS = (
    re.compile(r"(?i)\b(password|passwd|mot_de_passe)\b\s*[=:]\s*\S{6,}"),
    re.compile(r"(?i)\b(secret_key|secret|api[_-]?key|access[_-]?token|bearer)\b\s*[=:]\s*\S{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\."),  # en-tête de JWT
)

_ARTEFACTS_A_SCANNER = ["inventory", "entrypoints", "routes", "schema", "alembic-graph"]


def _valeurs_texte(noeud):
    """Toutes les chaînes d'un document JSON, quelle que soit leur profondeur.

    Balayer le fichier brut ne suffit pas : dans du JSON, un guillemet interne
    est échappé, et un motif comme `SECRET = "…"` s'écrit `SECRET = \\"…\\"`.
    Une expression régulière appliquée au texte brut le manque — ce qui donne
    un test rassurant et aveugle. On décode d'abord, on cherche ensuite.
    """
    if isinstance(noeud, str):
        yield noeud
    elif isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            yield str(cle)
            yield from _valeurs_texte(valeur)
    elif isinstance(noeud, list):
        for element in noeud:
            yield from _valeurs_texte(element)


@pytest.mark.parametrize("artefact", _ARTEFACTS_A_SCANNER)
def test_no_secret_or_real_data_in_the_artifacts(artefact):
    document = json.loads(_lire(ARTEFACTS / f"{artefact}.json"))
    for texte in _valeurs_texte(document):
        for motif in _MOTIFS_INTERDITS:
            trouve = motif.search(texte)
            assert not trouve, f"{artefact}.json : {trouve.group(0)[:60]}"


@pytest.mark.parametrize("artefact", _ARTEFACTS_A_SCANNER)
def test_the_artifacts_describe_structure_and_never_content(artefact):
    """Le catalogue est interrogé, jamais les tables.

    Un inventaire qui embarquerait des lignes de la base changerait de nature :
    il deviendrait un export de données, soumis à `REAL_DATA_NO_GO`.
    """
    document = json.loads(_lire(ARTEFACTS / f"{artefact}.json"))
    for cle in _valeurs_texte(document):
        assert cle not in ("rows", "sample_rows", "row_count", "data"), (
            f"{artefact}.json expose un contenu de table : {cle}"
        )


def test_the_generator_uses_synthetic_configuration_only():
    source = _lire(REPO_ROOT / "scripts" / "g0_inventory.py")
    assert "synthetic" in source.lower()
    assert "Aucun appel réseau. Aucun secret. Aucune donnée patient." in source


# ── documentation cohérente ─────────────────────────────────────────────────


def test_local_markdown_links_resolve():
    """Un lien mort dans une preuve rend la preuve invérifiable."""
    casses = []
    for document in sorted(DOCS.glob("*.md")):
        for cible in re.findall(r"\]\((?!https?://)([^)#]+)", _lire(document)):
            if not (document.parent / cible).resolve().exists():
                casses.append(f"{document.name} -> {cible}")
    assert not casses, f"liens locaux cassés : {casses}"


def test_the_inventory_confronts_preliminary_figures_with_generated_ones():
    """Un inventaire ajusté pour retomber sur un chiffre annoncé n'en est plus un."""
    aplati = _aplati(DOCS / "INVENTORY.md")
    assert "Chiffres préliminaires contre chiffres générés" in aplati
    assert "Ils n'étaient pas des cibles" in aplati


def test_findings_are_recorded_not_silently_fixed():
    """Le lot A photographie ; il ne corrige pas."""
    for document, phrase in (
        ("INVENTORY.md", "jamais corrigée en silence"),
        ("SCHEMA.md", "Constats transmis au lot D"),
        ("DEPLOYMENT_CSA_GR_PLATEAU.md", "Constats transmis au lot D"),
    ):
        assert phrase in _aplati(DOCS / document), f"{document} : « {phrase} » absent"


# ── invariants de gouvernance ───────────────────────────────────────────────


def test_governance_statuses_are_unchanged():
    gouvernance = REPO_ROOT / "docs" / "governance"
    assert (gouvernance / "CLINICAL_STATUS").read_text(encoding="utf-8").strip() == (
        "REAL_DATA_NO_GO"
    )
    assert (gouvernance / "DISTRIBUTION_STATUS").read_text(encoding="utf-8").strip() == (
        "DISTRIBUTION_NO_GO"
    )
    config = _lire(REPO_ROOT / "app" / "core" / "config.py")
    for reglage in (
        "CSA_SYNC_ENABLED: bool = False",
        "ENABLE_DH36_LISTENER: bool = False",
        "ANALYZER_RAW_LISTENER_ENABLED: bool = False",
    ):
        assert reglage in config, f"réglage modifié : {reglage}"


def test_the_inventory_records_the_governance_defaults(inventaire):
    reglages = {
        r["setting"]: r["default"] for r in inventaire["application"]["governance_defaults"]
    }
    assert reglages["CSA_SYNC_ENABLED"] == "False"
    assert reglages["ENABLE_DH36_LISTENER"] == "False"
    assert reglages["ANALYZER_RAW_LISTENER_ENABLED"] == "False"


# ── /app/map : ce que la page révèle réellement ─────────────────────────────
#
# La première rédaction de cette preuve affirmait que la page « ne révèle que
# l'existence de la fonctionnalité ». La réponse réellement servie contient
# davantage. Une qualification qui minimise ce qu'elle qualifie est pire qu'une
# absence de qualification : elle clôt l'examen.

#: Éléments présents dans le HTML public, vérifiés dans la réponse HTTP.
_CONTENU_PUBLIC_CARTE = (
    "Cartographie des EHM et Gendarmerie",
    "Établissements Hospitaliers Militaires",
    "DIVISION SANTÉ",
    "HMA",
    "CMA",
    "CSA",
    "Gendarmerie",
)

#: Effectifs agrégés, écrits en dur dans le gabarit.
_EFFECTIFS_PUBLICS = ("60", "1", "8", "51", "37", "22")


@pytest.fixture(scope="module")
def reponse_carte_sans_jeton():
    """`GET /app/map` sans en-tête `Authorization`, tel qu'un anonyme la reçoit."""
    from fastapi.testclient import TestClient

    from scripts.g0_inventory import _charger_application

    # Pas de `with` : le cycle de vie complet exigerait une configuration de
    # production. Ce qui est mesuré ici est la réponse du gabarit, pas le
    # démarrage de l'application.
    return TestClient(_charger_application()).get("/app/map")


def test_the_military_map_answers_unauthenticated_clients(reponse_carte_sans_jeton):
    assert reponse_carte_sans_jeton.status_code == 200


@pytest.mark.parametrize("element", _CONTENU_PUBLIC_CARTE)
def test_the_military_map_exposes_institutional_content(element, reponse_carte_sans_jeton):
    assert element in reponse_carte_sans_jeton.text, (
        f"« {element} » attendu dans la réponse publique de /app/map"
    )


def test_the_military_map_exposes_aggregate_headcounts(reponse_carte_sans_jeton):
    """Des effectifs en dur donnent un ordre de grandeur du dispositif."""
    corps = reponse_carte_sans_jeton.text
    for effectif in _EFFECTIFS_PUBLICS:
        assert f">{effectif}<" in corps, (
            f"effectif agrégé {effectif} attendu dans le gabarit public"
        )


def test_the_map_qualification_records_the_public_static_content():
    """La qualification doit citer ce qui est réellement exposé.

    Ce test échoue si la mention des contenus statiques est retirée du
    registre : c'est exactement la régression que la revue a relevée.
    """
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    entree = next(e for e in registre["qualified_routes"] if e["path"] == "/app/map")

    assert entree.get("public_static_content"), (
        "la qualification de /app/map ne cite aucun contenu statique public"
    )
    cite = " ".join(entree["public_static_content"]) + " " + entree["constat"]
    for terme in ("Cartographie", "Militaires", "HMA", "CMA", "CSA", "Gendarmerie"):
        assert terme in cite, f"contenu public non cité dans la qualification : {terme}"
    for effectif in _EFFECTIFS_PUBLICS:
        assert effectif in cite, f"effectif agrégé non cité dans la qualification : {effectif}"


def test_the_map_qualification_does_not_minimise_the_finding():
    """« Révèle seulement l'existence de la fonctionnalité » est faux ici."""
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    entree = next(e for e in registre["qualified_routes"] if e["path"] == "/app/map")
    texte = " ".join(
        (entree["constat"], entree["justification"], entree["risque_residuel"])
    ).lower()
    assert "revele la fonctionnalite" not in texte, (
        "la qualification minimise le constat : la page expose plus que l'existence "
        "de la fonctionnalité"
    )
    assert "categories institutionnelles" in texte
    assert "effectifs agreges" in texte


def test_the_map_finding_is_p1_and_not_invented_as_p0():
    """P0 exigerait une règle de classification institutionnelle qui n'existe pas."""
    registre = json.loads(_lire(DOCS / "ROUTE_EXPOSURE_QUALIFICATION.json"))
    entree = next(e for e in registre["qualified_routes"] if e["path"] == "/app/map")
    assert entree["classement"] == "P1"
    assert "lot D" in entree.get("remediation_owner", ""), (
        "la remédiation doit rester une action séparée"
    )


def test_the_routes_document_states_what_the_map_really_exposes():
    aplati = _aplati(DOCS / "ROUTES.md")
    assert "Le gabarit ne contient pas les coordonnées ni la liste détaillée des" in aplati
    assert "Il expose néanmoins publiquement la nature militaire de la" in aplati
    for effectif in ("60", "51", "37", "22"):
        assert effectif in aplati, f"effectif {effectif} absent de ROUTES.md"


def test_lot_a_does_not_remediate_the_map():
    """Le lot A photographie. Protéger la route ici masquerait le constat."""
    from scripts.g0_inventory import _charger_application, _dependances_de_route

    app = _charger_application()
    route = next(r for r in app.routes if getattr(r, "path", "") == "/app/map")
    assert not _dependances_de_route(route), (
        "/app/map a reçu une garde dans cette PR : la remédiation appartient au lot D, "
        "et corriger ici rendrait la preuve fausse"
    )


# ── provenance de qualité audit ─────────────────────────────────────────────


@pytest.mark.parametrize("fichier", ["provenance", "schema-provenance"])
def test_provenance_separates_what_is_compared_from_what_varies(fichier):
    entete = json.loads(_lire(ARTEFACTS / f"{fichier}.json"))
    assert set(entete) >= {"deterministic", "volatile"}, entete.keys()
    for champ in (
        "schema_version",
        "generator_version",
        "generation_command",
        "baseline_input_commit",
        "baseline_input_ref",
        "relevant_input_set",
        "relevant_input_file_count",
        "relevant_input_tree_sha256",
    ):
        assert entete["deterministic"].get(champ) not in (None, "", 0), (
            f"{fichier}.json : champ déterministe vide — {champ}"
        )
    assert entete["volatile"].get("generated_at")


@pytest.mark.parametrize("fichier", ["provenance", "schema-provenance"])
def test_provenance_never_cites_a_temporary_reference(fichier):
    """`tmp/g0-architecture-work` avait été inscrit comme source permanente."""
    entete = json.loads(_lire(ARTEFACTS / f"{fichier}.json"))["deterministic"]
    reference = entete["baseline_input_ref"]
    assert not reference.startswith(("tmp/", "wip/", "temp/")), (
        f"référence temporaire inscrite comme source permanente : {reference}"
    )
    assert reference in ("main", "master"), reference
    assert "source_git_ref" not in entete and "source_git_sha" not in entete, (
        "la nomenclature ambiguë subsiste"
    )


@pytest.mark.parametrize("fichier", ["provenance", "schema-provenance"])
def test_provenance_declares_an_explicit_baseline_commit(fichier):
    from scripts.g0_provenance import BASELINE_INPUT_COMMIT

    entete = json.loads(_lire(ARTEFACTS / f"{fichier}.json"))["deterministic"]
    commit = entete["baseline_input_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit), f"commit non résolu : {commit}"
    assert commit == BASELINE_INPUT_COMMIT


@pytest.mark.parametrize("fichier", ["provenance", "schema-provenance"])
def test_the_input_fingerprint_is_a_sha256(fichier):
    empreinte = json.loads(_lire(ARTEFACTS / f"{fichier}.json"))["deterministic"][
        "relevant_input_tree_sha256"
    ]
    assert re.fullmatch(r"[0-9a-f]{64}", empreinte), empreinte


@pytest.mark.parametrize("ensemble", ["inventory", "schema"])
def test_two_fingerprints_of_the_same_tree_are_equal(ensemble):
    from scripts.g0_provenance import empreinte_entrees

    assert empreinte_entrees(ensemble) == empreinte_entrees(ensemble)


def _faux_depot(racine):
    (racine / "alembic").mkdir(parents=True)
    (racine / "alembic" / "env.py").write_text("x = 1\n", encoding="utf-8")
    (racine / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (racine / "requirements.txt").write_text("alembic==1.0\n", encoding="utf-8")
    return racine


def test_changing_an_input_file_changes_the_fingerprint(tmp_path, monkeypatch):
    """Une empreinte insensible aux entrées ne prouverait rien."""
    import scripts.g0_provenance as provenance_module

    depot = _faux_depot(tmp_path / "depot")
    monkeypatch.setattr(provenance_module, "RACINE", depot)

    avant, nombre = provenance_module.empreinte_entrees("schema")
    (depot / "alembic" / "env.py").write_text("x = 2\n", encoding="utf-8")
    apres, nombre_apres = provenance_module.empreinte_entrees("schema")

    assert avant != apres, "un fichier d'entrée modifié laisse l'empreinte inchangée"
    assert nombre == nombre_apres == 3


def test_files_outside_the_input_set_do_not_change_the_fingerprint(tmp_path, monkeypatch):
    """Une empreinte qui bouge sans raison finit par être régénérée sans être lue."""
    import scripts.g0_provenance as provenance_module

    depot = _faux_depot(tmp_path / "depot2")
    monkeypatch.setattr(provenance_module, "RACINE", depot)

    avant, _ = provenance_module.empreinte_entrees("schema")
    (depot / "README.md").write_text("hors périmètre\n", encoding="utf-8")
    (depot / "docs").mkdir()
    (depot / "docs" / "note.md").write_text("hors périmètre\n", encoding="utf-8")

    assert provenance_module.empreinte_entrees("schema")[0] == avant


def test_build_artifacts_never_enter_the_fingerprint():
    """Sinon l'empreinte varierait selon qu'un test a tourné ou non."""
    from scripts.g0_provenance import fichiers_entree

    for ensemble in ("inventory", "schema"):
        for chemin in fichiers_entree(ensemble):
            assert "__pycache__" not in chemin.parts
            assert chemin.suffix not in (".pyc", ".pyo")


def test_check_detects_a_stale_provenance(tmp_path):
    """Une provenance figée décrirait un état révolu, en silence."""
    from scripts.g0_inventory import main, provenance

    for nom in ("inventory", "entrypoints", "routes"):
        (tmp_path / f"{nom}.json").write_text(_lire(ARTEFACTS / f"{nom}.json"), encoding="utf-8")
    perimee = provenance("python scripts/g0_inventory.py --generate")
    perimee["deterministic"]["relevant_input_tree_sha256"] = "0" * 64
    (tmp_path / "provenance.json").write_text(json.dumps(perimee), encoding="utf-8")

    assert main(["--check", "--output-dir", str(tmp_path)]) == 1


# ── références d'image Compose ──────────────────────────────────────────────

_VARIABLE = "RUGGYLAB_IMAGE"
_MESSAGE_AVEC_EXEMPLE = "${" + _VARIABLE + ":?must be set (e.g. ghcr.io/org/app:<git-sha>)}"


@pytest.mark.parametrize(
    ("reference", "attendu"),
    [
        (
            "postgres:16.6-alpine",
            {"kind": "static", "registry": None, "repository": "postgres", "tag": "16.6-alpine"},
        ),
        (
            "ghcr.io/rommellnelson-ux/ruggylab-os:v0.8.0",
            {
                "kind": "static",
                "registry": "ghcr.io",
                "repository": "rommellnelson-ux/ruggylab-os",
                "tag": "v0.8.0",
            },
        ),
        ("valkey/valkey:8.1.9-alpine", {"kind": "static", "repository": "valkey/valkey"}),
        ("postgres", {"kind": "static", "tag": None, "repository": "postgres"}),
        ("registry.local:5000/equipe/service", {"kind": "static", "tag": None}),
        ("${" + _VARIABLE + "}", {"kind": "dynamic_environment_expression", "tag": None}),
        (
            "${" + _VARIABLE + ":-ruggylab:dev}",
            {"kind": "dynamic_environment_expression", "tag": None},
        ),
        (
            "${" + _VARIABLE + ":?" + _VARIABLE + " must be set}",
            {"kind": "dynamic_environment_expression", "tag": None},
        ),
        (_MESSAGE_AVEC_EXEMPLE, {"kind": "dynamic_environment_expression", "tag": None}),
        ("", {"kind": "built_from_dockerfile", "tag": None}),
    ],
)
def test_image_references_are_parsed_or_declared_dynamic(reference, attendu):
    """Découper sur le dernier « : » traitait un message d'erreur comme un tag."""
    from scripts.g0_inventory import _analyser_reference_image

    obtenu = _analyser_reference_image(reference)
    assert obtenu["image_reference_kind"] == attendu["kind"], reference
    for cle, valeur in attendu.items():
        if cle != "kind":
            assert obtenu[cle] == valeur, f"{reference} : {cle} = {obtenu[cle]!r}"


def test_a_digest_is_extracted_alongside_its_tag():
    from scripts.g0_inventory import _analyser_reference_image

    analyse = _analyser_reference_image("valkey/valkey:8.1.9-alpine@sha256:" + "e" * 64)
    assert analyse["tag"] == "8.1.9-alpine"
    assert analyse["digest"] == "sha256:" + "e" * 64


def test_a_dynamic_reference_names_its_variable_and_invents_nothing():
    from scripts.g0_inventory import _analyser_reference_image

    modele = "${" + _VARIABLE + ":?" + _VARIABLE + " must be set}"
    analyse = _analyser_reference_image(modele)
    assert analyse["required_variable"] == _VARIABLE
    assert analyse["image_template"] == modele
    assert analyse["resolved_image"] is None
    assert analyse["registry"] is analyse["repository"] is analyse["tag"] is None


def test_no_compose_service_carries_a_fabricated_tag(inventaire):
    """Un tag issu d'un message Compose est un fait inventé."""
    fautifs = [
        (fichier["file"], service["service"], service["tag"])
        for fichier in inventaire["compose"]
        for service in fichier["services"]
        if service["tag"] and any(c in service["tag"] for c in " ${}?<>()")
    ]
    assert not fautifs, f"tags fabriqués : {fautifs}"


def test_dynamic_references_are_declared_as_such(inventaire):
    dynamiques = [
        service
        for fichier in inventaire["compose"]
        for service in fichier["services"]
        if service["image_reference_kind"] == "dynamic_environment_expression"
    ]
    assert dynamiques, "aucune référence dynamique recensée alors que le cœur en contient"
    for service in dynamiques:
        assert service["tag"] is None and service["resolved_image"] is None
        assert service["required_variable"], service["service"]


# ── définitions de services contre services nominaux ────────────────────────


def test_core_counts_distinguish_definitions_from_running_services(inventaire, compose_coeur):
    """« 9 services dans le cœur » surestimait la surface permanente d'un conteneur."""
    coeur = inventaire["core_services"]
    assert len(coeur["service_definitions"]) == len(compose_coeur["services"]) == 9
    assert len(coeur["nominal_running_services"]) == 8
    assert coeur["one_shot_profile_services"] == ["migrate"]
    assert set(coeur["nominal_running_services"]) | set(coeur["one_shot_profile_services"]) == set(
        coeur["service_definitions"]
    )


def test_a_profiled_service_is_not_counted_as_a_permanent_container(inventaire):
    assert "migrate" not in inventaire["core_services"]["nominal_running_services"]


def test_a_profiled_service_is_still_inventoried(inventaire):
    """Le retirer masquerait un point d'entrée réel."""
    assert "migrate" in inventaire["core_services"]["service_definitions"]
    fichier = next(f for f in inventaire["compose"] if f["status"] == "core")
    migrate = next(s for s in fichier["services"] if s["service"] == "migrate")
    assert migrate["runtime_kind"] == "one_shot_profile_task"
    assert migrate["started_by_default"] is False
    assert migrate["profiles"] == ["migrate"]


def test_every_compose_file_reports_both_counts(inventaire):
    for fichier in inventaire["compose"]:
        assert fichier["service_definitions"] == len(fichier["services"])
        assert fichier["nominal_running_services"] <= fichier["service_definitions"]


def test_the_c4_marks_the_migration_task_as_one_shot():
    """Un diagramme qui montre `migrate` comme un service permanent ment."""
    diagramme = _diagramme_conteneurs()
    ligne = next(ligne for ligne in diagramme.splitlines() if ligne.strip().startswith("MIG["))
    assert "ponctuelle" in ligne, ligne
    assert "NON DÉMARRÉ PAR DÉFAUT" in ligne


def test_the_documents_no_longer_claim_nine_running_services():
    for nom in ("INVENTORY.md", "C4.md"):
        aplati = _aplati(DOCS / nom)
        assert "Neuf services" not in aplati, f"{nom} : comptage non qualifié"
        assert "définitions de services" in aplati.lower(), nom


# ── classification documentaire ─────────────────────────────────────────────

_DOCUMENTS_ARCHITECTURE = ["C4.md", "DEPLOYMENT_CSA_GR_PLATEAU.md", "ROUTES.md", "SCHEMA.md"]


@pytest.mark.parametrize("document", _DOCUMENTS_ARCHITECTURE)
def test_architecture_documents_carry_their_classification(document):
    entete = _aplati(DOCS / document)[:900]
    assert "INTERNAL — SECURITY ARCHITECTURE" in entete, document
    assert "BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT" in entete, document


@pytest.mark.parametrize("document", _DOCUMENTS_ARCHITECTURE)
def test_the_classification_banner_does_not_pretend_to_be_a_control(document):
    """Un bandeau n'empêche personne de lire un dépôt public."""
    assert "mention de classification, pas un contrôle d'accès" in _aplati(DOCS / document)


@pytest.mark.parametrize("document", _DOCUMENTS_ARCHITECTURE)
def test_no_real_site_address_in_the_architecture_documents(document):
    """Tant que le dépôt est public, aucun détail opérationnel réel."""
    contenu = _lire(DOCS / document)
    for adresse in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", contenu):
        assert adresse in ("127.0.0.1", "0.0.0.0", "255.255.255.255"), (
            f"{document} : adresse IP potentiellement réelle — {adresse}"
        )


def test_the_input_order_does_not_depend_on_the_platform():
    """L'ordre entre dans l'empreinte : il doit être identique partout.

    `sorted()` sur des objets `Path` replie la casse sous Windows et la
    respecte sous Linux — `Dockerfile` passe alors avant ou après
    `alembic/env.py` selon la machine, pour un contenu identique. La CI Linux a
    refusé une baseline générée sous Windows pour cette seule raison.
    """
    from scripts.g0_provenance import chemin_relatif, fichiers_entree

    for ensemble in ("inventory", "schema"):
        chemins = [chemin_relatif(p) for p in fichiers_entree(ensemble)]
        assert chemins == sorted(chemins), (
            f"{ensemble} : ordre dépendant de la plateforme — "
            f"premier écart vers {next(a for a, b in zip(chemins, sorted(chemins), strict=True) if a != b)}"
        )


def test_the_fingerprint_covers_the_path_as_well_as_the_content(tmp_path, monkeypatch):
    """Deux fichiers dont on échange le contenu doivent changer l'empreinte."""
    import scripts.g0_provenance as provenance_module

    depot = tmp_path / "depot3"
    (depot / "alembic").mkdir(parents=True)
    (depot / "alembic" / "a.py").write_text("contenu A\n", encoding="utf-8")
    (depot / "alembic" / "b.py").write_text("contenu B\n", encoding="utf-8")
    (depot / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (depot / "requirements.txt").write_text("alembic==1.0\n", encoding="utf-8")
    monkeypatch.setattr(provenance_module, "RACINE", depot)

    avant, _ = provenance_module.empreinte_entrees("schema")
    (depot / "alembic" / "a.py").write_text("contenu B\n", encoding="utf-8")
    (depot / "alembic" / "b.py").write_text("contenu A\n", encoding="utf-8")

    assert provenance_module.empreinte_entrees("schema")[0] != avant

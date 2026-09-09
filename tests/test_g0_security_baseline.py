"""Tests — la baseline de sécurité G0 décrit le code, et le dit encore demain.

Ces tests portent sur les preuves du **lot B** : matrice RBAC, sondes
d'autorisation, routes particulières, classification des données, flux externes,
sentinelles de journalisation, audit de `.secrets.baseline` et barrière de
secrets.

Deux principes de rédaction, tirés du refus du lot A.

1. **Un test qui lit un artefact versionné ne prouve rien sur le générateur.**
   Muter le générateur sans régénérer laisserait le test vert. Les affirmations
   qui comptent sont donc vérifiées **deux fois** : sur le fichier versionné, et
   sur un payload reconstruit dans le processus de test.
2. **Une preuve ne minimise pas ce qu'elle décrit.** Plusieurs tests échouent
   précisément si une qualification est adoucie — c'est la régression que la
   revue du lot A avait relevée sur `/app/map`.

Le lot B photographie. Aucun test ici ne demande qu'un défaut soit corrigé : il
demande qu'il reste décrit.
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
GOUVERNANCE = REPO_ROOT / "docs" / "governance"

#: Les artefacts produits par le lot B, et eux seuls.
ARTEFACTS_LOT_B = (
    "rbac-matrix",
    "data-classification",
    "external-flows",
    "log-sentinel-observations",
    "secret-scan-summary",
)

#: Les quatre documents du lot B.
DOCUMENTS_LOT_B = (
    "RBAC.md",
    "DATA_AND_FLOWS.md",
    "SECRET_SCANNING.md",
    "SECURITY_FINDINGS.md",
)


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _payload(nom: str):
    chemin = ARTEFACTS / f"{nom}.json"
    assert chemin.is_file(), f"artefact G0 absent : {chemin}"
    return json.loads(_lire(chemin))["payload"]


def _aplati(chemin: Path) -> str:
    """Le texte d'un document, débarrassé de sa mise en forme Markdown.

    Une phrase coupée par un retour à la ligne ne doit pas faire échouer un test
    qui la cherche : ce serait faire dépendre une preuve de la largeur de ses
    lignes.
    """
    lignes = [re.sub(r"^\s*>\s?", "", ligne) for ligne in _lire(chemin).splitlines()]
    return " ".join(" ".join(lignes).replace("*", "").replace("`", "").split())


@pytest.fixture(scope="module")
def rbac():
    return _payload("rbac-matrix")


@pytest.fixture(scope="module")
def classification():
    return _payload("data-classification")


@pytest.fixture(scope="module")
def flux():
    return _payload("external-flows")


@pytest.fixture(scope="module")
def sentinelles():
    return _payload("log-sentinel-observations")


@pytest.fixture(scope="module")
def secrets_resume():
    return _payload("secret-scan-summary")


@pytest.fixture(scope="module")
def construit():
    """Un payload reconstruit **dans ce processus**, sondes comprises.

    C'est lui qui rend les mutations du générateur détectables : un test qui ne
    lirait que `artifacts/g0/` resterait vert alors que le code aurait changé.
    """
    from scripts.g0_security_baseline import construire

    return construire()


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "ci.yml"))


# ── déterminisme : sans lui, `--check` ne prouve rien ───────────────────────


def test_two_generations_produce_the_same_payload():
    """Un payload instable rendrait `--check` inutilisable.

    Les sondes tournent contre une application réelle : si leur résultat variait
    d'une exécution à l'autre, le contrôle échouerait toujours, on l'ignorerait,
    et la baseline dériverait sans obstacle.
    """
    from scripts.g0_security_baseline import construire

    premier = json.dumps(construire(), sort_keys=True, ensure_ascii=False)
    second = json.dumps(construire(), sort_keys=True, ensure_ascii=False)
    assert premier == second, "deux générations successives divergent"


def test_the_versioned_artifacts_match_a_fresh_build(construit):
    """Les fichiers versionnés décrivent le code d'aujourd'hui, pas d'hier."""
    for nom in ARTEFACTS_LOT_B:
        assert _payload(nom) == construit[nom], (
            f"{nom}.json ne correspond plus à ce que le générateur produit — "
            "régénérer avec : python scripts/g0_security_baseline.py --generate"
        )


def test_volatile_fields_live_outside_the_compared_payload():
    """L'heure de génération ne doit pas provoquer un diff permanent."""
    from scripts.g0_security_baseline import provenance

    entete = provenance("test")
    assert "generated_at" in entete["volatile"]
    assert "generated_at" not in entete["deterministic"]
    for nom in ARTEFACTS_LOT_B:
        assert "generated_at" not in json.dumps(_payload(nom)), f"{nom}.json porte un champ volatil"


def test_check_detects_a_divergence(tmp_path):
    """Un contrôle qui ne détecte rien ne protège de rien.

    Une opération est retirée de la matrice recopiée : `--check` doit refuser.
    """
    from scripts.g0_security_baseline import main

    for nom in (*ARTEFACTS_LOT_B, "security-provenance"):
        source = json.loads(_lire(ARTEFACTS / f"{nom}.json"))
        if nom == "rbac-matrix":
            source["payload"]["operations"] = source["payload"]["operations"][:-1]
        (tmp_path / f"{nom}.json").write_text(json.dumps(source), encoding="utf-8")
    assert main(["--check", "--output-dir", str(tmp_path)]) == 1


def test_check_detects_a_softened_qualification(tmp_path):
    """Adoucir une qualification est la régression que la revue a relevée."""
    from scripts.g0_security_baseline import main

    for nom in (*ARTEFACTS_LOT_B, "security-provenance"):
        source = json.loads(_lire(ARTEFACTS / f"{nom}.json"))
        if nom == "rbac-matrix":
            for route in source["payload"]["special_routes"]:
                if route["route"] == "GET /app/map":
                    route["constat"] = "Ne revele que l'existence de la fonctionnalite."
        (tmp_path / f"{nom}.json").write_text(json.dumps(source), encoding="utf-8")
    assert main(["--check", "--output-dir", str(tmp_path)]) == 1


def test_check_passes_on_the_versioned_artifacts():
    from scripts.g0_security_baseline import main

    assert main(["--check"]) == 0


# ── couverture de la matrice ────────────────────────────────────────────────


def test_the_matrix_covers_every_openapi_operation(rbac):
    """231 opérations recensées par le lot A, 231 qualifiées. Aucune omission."""
    routes = json.loads(_lire(ARTEFACTS / "routes.json"))["payload"]
    attendues = {(o["method"], o["path"]) for o in routes["operations"]}
    obtenues = {(o["method"], o["path"]) for o in rbac["operations"]}
    assert obtenues == attendues, f"écart de couverture : {attendues ^ obtenues}"
    assert len(rbac["operations"]) == 231
    assert rbac["totals"]["operations"] == 231


def test_the_matrix_covers_every_operation_in_a_fresh_build(construit):
    assert len(construit["rbac-matrix"]["operations"]) == 231


def test_no_operation_is_left_unresolved(rbac):
    """`UNRESOLVED` serait un aveu d'ignorance : il ne doit en rester aucun."""
    non_resolues = [o for o in rbac["operations"] if o["confidence"] == "UNRESOLVED"]
    assert non_resolues == [], f"opérations non qualifiées : {non_resolues}"
    assert rbac["totals"]["unresolved"] == 0


def test_every_operation_carries_a_written_justification(rbac):
    """Une qualification sans motif n'est pas une qualification."""
    muettes = [
        f"{o['method']} {o['path']}"
        for o in rbac["operations"]
        if not str(o.get("justification", "")).strip()
    ]
    assert muettes == [], f"opérations sans justification : {muettes[:10]}"


@pytest.mark.parametrize(
    ("niveau", "total"),
    [("STATIC_EXPLICIT", 168), ("RUNTIME_CONFIRMED", 62), ("CUSTOM_AUTH_CONFIRMED", 1)],
)
def test_the_confidence_counts_are_the_measured_ones(rbac, niveau, total):
    """Les chiffres du document viennent de la mesure, jamais d'une estimation."""
    assert rbac["totals"]["by_confidence"][niveau] == total
    assert sum(1 for o in rbac["operations"] if o["confidence"] == niveau) == total


def test_the_confidence_counts_sum_to_the_operation_count(rbac):
    assert sum(rbac["totals"]["by_confidence"].values()) == 231


def test_authentication_guards_are_not_counted_as_authorization(rbac):
    """`get_current_user` n'autorise rien : le confondre gonflerait la matrice."""
    for nom in ("get_current_user", "get_current_active_user"):
        assert rbac["guard_semantics"][nom]["nature"] == "authentication"
        assert sorted(rbac["guard_semantics"][nom]["roles_autorises"]) == [
            "accountant",
            "admin",
            "officer",
            "technician",
        ]


def test_the_operations_with_authentication_only_are_named(rbac):
    """51 opérations n'exercent aucun contrôle de rôle — le dire, pas l'arrondir."""
    auth_seule = [
        o for o in rbac["operations"] if o["authorization_source"] == "authentication_only"
    ]
    assert len(auth_seule) == 51
    assert rbac["totals"]["authentication_only"] == 51


# ── sondes dynamiques par rôle ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def sondes(rbac):
    return rbac["runtime_probes"]["probes"]


def test_the_probes_ran_for_every_role(sondes):
    """Une matrice sondée pour un seul rôle ne dit rien de la séparation des tâches."""
    comptes = {s["account"] for s in sondes}
    for attendu in ("admin", "officer", "technician", "accountant", "technician_unit_a"):
        assert attendu in comptes, f"aucune sonde pour le compte {attendu}"
    assert "<anonyme>" in comptes, "aucune sonde anonyme"


@pytest.mark.parametrize(
    ("compte", "total"),
    [
        ("admin", 8),
        ("officer", 20),
        ("technician", 29),
        ("technician_unit_a", 4),
        ("accountant", 32),
        ("<anonyme>", 6),
    ],
)
def test_the_probe_counts_per_account_are_the_measured_ones(sondes, compte, total):
    assert sum(1 for s in sondes if s["account"] == compte) == total


def test_every_role_was_probed_in_both_directions(sondes):
    """Sonder uniquement ce qui doit passer ne prouve pas qu'un refus existe."""
    for compte in ("officer", "technician", "accountant"):
        attendus = {s["expected"] for s in sondes if s["account"] == compte}
        assert attendus == {"ALLOW", "DENY"}, f"{compte} : sondes à sens unique ({attendus})"


def test_anonymous_probes_are_all_denied(sondes):
    anonymes = [s for s in sondes if s["account"] == "<anonyme>"]
    assert anonymes, "aucune sonde anonyme"
    for sonde in anonymes:
        assert sonde["outcome"] == "DENIED", f"anonyme accepté sur {sonde['path']}"
        assert sonde["observed_status"] == 401


def test_the_probe_totals_are_consistent(rbac, sondes):
    totaux = rbac["runtime_probes"]["totals"]
    assert totaux["probes"] == len(sondes) == 99
    assert (
        totaux["matching_expectation"] == sum(1 for s in sondes if s["matches_expectation"]) == 96
    )


def test_a_probe_stopped_by_validation_is_not_counted_as_authorization(sondes):
    """Un 422 avant l'autorisation n'est pas une preuve d'autorisation."""
    avant = [s for s in sondes if s["probe_class"] == "VALIDATION_FAILED_BEFORE_AUTHORIZATION"]
    assert len(avant) == 1
    assert avant[0]["observed_status"] == 422
    assert sum(1 for s in sondes if s["probe_class"] == "AUTHORIZATION_REACHED") == 98


#: Les trois écarts mesurés. Les retirer sans que l'application change ferait
#: disparaître un constat P1 : ce test l'interdit.
_ECARTS_ATTENDUS = {
    ("accountant", "POST", "/api/v1/aes", 201),
    ("accountant", "POST", "/api/v1/quality/non-conformities", 201),
    ("technician", "POST", "/api/v1/billing/calculate", 200),
}


def test_the_three_measured_deviations_are_recorded(sondes):
    ecarts = {
        (s["account"], s["method"], s["path"], s["observed_status"])
        for s in sondes
        if not s["matches_expectation"]
    }
    assert ecarts == _ECARTS_ATTENDUS


def test_the_deviations_are_measured_again_by_a_fresh_build(construit):
    """Sur le payload reconstruit : c'est l'application qui répond, pas le fichier."""
    ecarts = {
        (s["account"], s["method"], s["path"], s["observed_status"])
        for s in construit["rbac-matrix"]["runtime_probes"]["probes"]
        if not s["matches_expectation"]
    }
    assert ecarts == _ECARTS_ATTENDUS


def test_the_accountant_really_reaches_the_blood_exposure_register(construit):
    """Sonde rejouée en direct : le comptable crée bien un dossier AES.

    Ce dossier porte le statut sérologique VIH/VHB/VHC du patient source. Si
    cette sonde cessait d'aboutir sans qu'aucun code ne change, c'est la mesure
    qui serait fausse.
    """
    sondes = construit["rbac-matrix"]["runtime_probes"]["probes"]
    aes = [
        s
        for s in sondes
        if s["account"] == "accountant" and s["method"] == "POST" and s["path"] == "/api/v1/aes"
    ]
    assert len(aes) == 1
    assert aes[0]["observed_status"] == 201
    assert aes[0]["outcome"] == "REACHED_HANDLER"
    assert aes[0]["expected"] == "DENY"


# ── routes particulières ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def particulieres(rbac):
    return {r["route"]: r for r in rbac["special_routes"]}


_ROUTES_PARTICULIERES = (
    "GET /app/map",
    "GET /api/v1/reports/verify/{token}",
    "POST /api/v1/login/refresh",
    "POST /api/v1/login/logout",
    "POST /api/v1/analyzer/results",
    "WEBSOCKET /api/v1/notifications/ws",
    "OPTIONS /{path_name:path} (attrape-tout)",
    "GET /metrics, /docs, /redoc, /openapi.json",
)


@pytest.mark.parametrize("route", _ROUTES_PARTICULIERES)
def test_every_special_route_is_qualified(particulieres, route):
    assert route in particulieres, f"route particulière non qualifiée : {route}"


@pytest.mark.parametrize("route", _ROUTES_PARTICULIERES)
def test_every_special_route_states_its_real_capacity(particulieres, route):
    """Une qualification sans capacité réelle ni classement n'en est pas une."""
    entree = particulieres[route]
    for champ in (
        "capacite_reelle",
        "classement",
        "constat",
        "expiration",
        "mecanisme_de_garde",
        "portee",
        "rejeu_possible",
        "traces_journaux",
    ):
        assert str(entree.get(champ, "")).strip(), f"{route} : champ « {champ} » vide"
    assert entree["classement"] in ("P0", "P1", "P2")


# ── /app/map : le constat accepté au lot A, conservé mot pour mot ───────────
#
# La première rédaction du lot A affirmait que la page « ne révèle que
# l'existence de la fonctionnalité ». C'était faux. Le lot B reprend le constat
# corrigé ; ces tests interdisent qu'il soit à nouveau adouci.

_CONTENU_PUBLIC_CARTE = (
    "Cartographie des EHM et Gendarmerie",
    "Établissements Hospitaliers Militaires",
    "DIVISION SANTÉ",
    "HMA",
    "CMA",
    "CSA",
    "Gendarmerie",
)

_EFFECTIFS_PUBLICS = ("60", "1", "8", "51", "37", "22")


def test_the_military_map_is_still_reachable_without_a_token(particulieres):
    carte = particulieres["GET /app/map"]
    assert carte["observed_status_sans_jeton"] == 200
    assert carte["jeton_utilise"] is None
    assert carte["rejeu_possible"] is True


@pytest.mark.parametrize("element", _CONTENU_PUBLIC_CARTE)
def test_the_map_qualification_names_what_is_exposed(particulieres, element):
    carte = particulieres["GET /app/map"]
    cite = carte["constat"] + " " + " ".join(map(str, carte["informations_retournees"]))
    assert element in cite, f"contenu public non cité : {element}"


@pytest.mark.parametrize("effectif", _EFFECTIFS_PUBLICS)
def test_the_map_qualification_names_the_aggregate_headcounts(particulieres, effectif):
    carte = particulieres["GET /app/map"]
    cite = carte["constat"] + " " + " ".join(map(str, carte["informations_retournees"]))
    assert effectif in cite, f"effectif agrégé non cité : {effectif}"


def test_the_map_qualification_does_not_minimise_the_finding(particulieres):
    carte = particulieres["GET /app/map"]
    texte = (carte["constat"] + " " + carte["capacite_reelle"]).lower()
    assert "seule existence" not in texte
    assert "uniquement l'existence" not in texte
    assert "sans coordonnées ni liste détaillée" in carte["constat"].lower()


def test_the_map_finding_stays_p1(particulieres):
    """P0 exigerait une règle de classification institutionnelle qui n'existe pas."""
    assert particulieres["GET /app/map"]["classement"] == "P1"


def test_lot_b_does_not_remediate_the_map():
    """Le lot B photographie. Protéger la route ici masquerait le constat."""
    from scripts.g0_inventory import _charger_application, _dependances_de_route

    application = _charger_application()
    route = next(r for r in application.routes if getattr(r, "path", "") == "/app/map")
    assert not _dependances_de_route(route), (
        "/app/map a reçu une garde dans cette PR : la remédiation appartient au lot D"
    )


# ── les autres routes particulières, sur ce qui a été mesuré ────────────────


def test_the_report_verification_token_never_expires(particulieres):
    entree = particulieres["GET /api/v1/reports/verify/{token}"]
    assert entree["expiration"].startswith("AUCUNE")
    assert entree["rejeu_possible"] is True
    assert entree["observed_status_jeton_inexistant"] == 404
    assert "chemin" in entree["traces_journaux"].lower()


def test_the_analyzer_ingestion_is_fail_closed(particulieres):
    """La réserve du lot A est levée : sans clé, la route refuse."""
    entree = particulieres["POST /api/v1/analyzer/results"]
    assert entree["observed_status_sans_cle"] == 503
    assert entree["classement"] == "P2"


def test_the_refresh_route_rejects_an_unknown_token(particulieres):
    entree = particulieres["POST /api/v1/login/refresh"]
    assert entree["observed_status_jeton_inexistant"] == 401
    assert entree["rejeu_possible"] is False


def test_the_logout_route_does_not_leak_whether_a_token_existed(particulieres):
    entree = particulieres["POST /api/v1/login/logout"]
    assert entree["observed_status_anonyme_corps_vide"] == 204
    assert entree["observed_status_anonyme_jeton_inexistant"] == 204


def test_the_websocket_gap_on_auth_version_is_recorded(particulieres):
    entree = particulieres["WEBSOCKET /api/v1/notifications/ws"]
    assert "auth_version" in entree["constat"]
    assert entree["observed_refus_sans_jeton"] is True


def test_the_technical_surfaces_answer_directly_on_the_application(particulieres):
    """Le blocage est au proxy, pas dans l'application : le dire, pas l'inverser."""
    entree = particulieres["GET /metrics, /docs, /redoc, /openapi.json"]
    observés = entree["observed_status_en_direct_sur_l_application"]
    assert observés == {"/docs": 200, "/metrics": 200, "/openapi.json": 200, "/redoc": 200}
    assert entree["proxy_bloque"] is True
    assert "aucun côté application" in entree["mecanisme_de_garde"]


# ── classification et flux ──────────────────────────────────────────────────


def test_every_column_of_the_migrated_schema_is_classified(classification):
    """Classer 519 colonnes sur 519 : une colonne oubliée serait une zone d'ombre."""
    schema = json.loads(_lire(ARTEFACTS / "schema.json"))["payload"]
    colonnes = len(schema["columns"])
    assert classification["totals"]["fields"] == colonnes == 519
    assert len(classification["fields"]) == colonnes


def test_the_actors_are_computed_from_the_matrix_not_asserted(classification):
    """Affirmer qui atteint une table, sans le dériver, serait invérifiable."""
    for table, details in classification["table_actors"].items():
        assert details["derivation"], f"{table} : acteurs sans dérivation"
        assert details["route_count"] == len(details["routes"])


def test_the_absence_of_retention_policy_is_measured(classification):
    assert classification["totals"]["fields_without_retention_policy"] == 493


def test_the_free_text_fields_stay_to_be_qualified(classification):
    """Classer un champ texte libre `NON_SENSIBLE` serait une affirmation gratuite."""
    assert classification["totals"]["by_category"]["A_QUALIFIER"] == 16


def test_every_external_flow_states_its_default_state(flux):
    assert flux["totals"]["flows"] == len(flux["flows"]) == 17
    for frontiere in flux["flows"]:
        for champ in ("etat_par_defaut", "categories_donnees", "chiffrement", "risque_residuel"):
            assert str(frontiere.get(champ, "")).strip(), f"{frontiere['id']} : « {champ} » vide"


def test_the_flows_that_would_export_data_are_disabled_by_default(flux):
    """Deux frontières feraient sortir des données nominatives. Elles sont coupées."""
    par_id = {f["id"]: f for f in flux["flows"]}
    assert "DESACTIVEE" in par_id["csa_supabase"]["etat_par_defaut"]
    assert "CSA_SYNC_ENABLED=false" in par_id["csa_supabase"]["etat_par_defaut"]
    assert "DESACTIVES" in par_id["automates_desactives"]["etat_par_defaut"]


def test_the_unencrypted_backup_is_not_softened(flux):
    """Une sauvegarde non chiffrée de toute la base est le risque le plus lourd."""
    sauvegarde = next(f for f in flux["flows"] if f["id"] == "sauvegardes")
    assert "aucun" in sauvegarde["chiffrement"].lower()
    assert "non chiffr" in sauvegarde["risque_residuel"].lower()


# ── sentinelles de journalisation ───────────────────────────────────────────


def test_the_sentinels_were_searched_on_every_declared_surface(sentinelles):
    attendu = len(sentinelles["sentinelles_declarees"]) * len(sentinelles["surfaces_examinees"])
    assert sentinelles["totals"]["observations"] == attendu == 70
    assert len(sentinelles["observations"]) == attendu


def test_the_sentinel_values_are_absent_from_the_artifact(sentinelles):
    """Écrire la valeur cherchée la rendrait indétectable par un futur contrôle."""
    from scripts.g0_security_baseline import SENTINELLES

    corps = json.dumps(sentinelles, ensure_ascii=False)
    for valeur in SENTINELLES.values():
        assert valeur not in corps, "une valeur de sentinelle a été recopiée dans l'artefact"


#: Ce qui a réellement été retrouvé. Ni plus — ce serait alarmiste — ni moins —
#: ce serait une preuve fausse.
_SENTINELLES_TROUVEES = {
    ("code_barres", "journal_application"),
    ("code_barres", "messages_erreur_client"),
    ("ipp", "audit_metier_en_base"),
    ("ipp", "messages_erreur_client"),
    ("jeton_verification", "journal_application"),
    ("prenom", "messages_erreur_client"),
}


def test_the_found_sentinels_are_exactly_the_measured_ones(sentinelles):
    trouvees = {(o["sentinel"], o["surface"]) for o in sentinelles["observations"] if o["found"]}
    assert trouvees == _SENTINELLES_TROUVEES
    assert sentinelles["totals"]["trouvees"] == 6


def test_the_found_sentinels_are_measured_again_by_a_fresh_build(construit):
    trouvees = {
        (o["sentinel"], o["surface"])
        for o in construit["log-sentinel-observations"]["observations"]
        if o["found"]
    }
    assert trouvees == _SENTINELLES_TROUVEES


def test_the_verification_token_is_found_in_the_application_log(sentinelles):
    """Le constat B-03 tient à cette observation : elle ne doit pas disparaître."""
    observation = next(
        o
        for o in sentinelles["observations"]
        if o["sentinel"] == "jeton_verification" and o["surface"] == "journal_application"
    )
    assert observation["found"] is True


def test_no_sentinel_reaches_the_metrics(sentinelles):
    """Point positif, et mesuré : l'étiquette porte le gabarit, pas le chemin."""
    for o in sentinelles["observations"]:
        if o["surface"] in ("metriques_prometheus", "etiquettes_de_metriques"):
            assert o["found"] is False, f"sentinelle {o['sentinel']} dans {o['surface']}"


def test_the_proxy_log_surface_is_declared_as_not_exercised(sentinelles):
    """Une surface non exercée doit être dite telle, pas comptée comme propre."""
    proxy = sentinelles["surface_journal_proxy"]
    assert proxy["exercee"] is False
    assert proxy["directive_log_presente"] is False


# ── audit de `.secrets.baseline` ────────────────────────────────────────────


def test_the_secret_review_never_reproduces_a_value(secrets_resume):
    """Un fragment de secret reste un indice : l'artefact n'en porte aucun."""
    for entree in secrets_resume["entries"]:
        assert set(entree) == {
            "rule",
            "file",
            "line",
            "is_verified",
            "status",
            "character",
            "justification",
            "rotation_required",
        }


def test_every_baseline_entry_is_reviewed(secrets_resume):
    assert secrets_resume["unreviewed_files"] == []
    assert all(e["status"] == "ACCEPTE" for e in secrets_resume["entries"])
    assert secrets_resume["totals"]["real_secrets"] == 0
    assert secrets_resume["totals"]["rotation_required"] == 0


def test_the_windows_style_paths_of_the_baseline_are_recorded(secrets_resume):
    """13 clés sur 14 ne s'appliquent jamais sur un runner Linux. C'est un constat."""
    assert len(secrets_resume["windows_style_paths_normalised"]) == 13


def test_the_baseline_file_itself_is_left_untouched():
    """Le lot B qualifie ; réécrire la baseline serait une remédiation."""
    baseline = json.loads(_lire(REPO_ROOT / ".secrets.baseline"))
    windows = [c for c in baseline["results"] if "\\" in c]
    assert len(windows) == 13, (
        "`.secrets.baseline` a été réécrit : la correction appartient au lot D, "
        "et la corriger ici rendrait le constat invérifiable"
    )


# ── barrière de secrets : non-vacuité et couverture ─────────────────────────


def test_the_secret_probes_are_not_vacuous():
    """Un scanner muet et un dépôt propre produisent le même vert.

    La sonde écrit, hors du dépôt, un fichier porteur d'une sentinelle qui DOIT
    être détectée et un fichier propre qui ne doit PAS l'être.
    """
    from scripts.g0_secret_gate import sonde_detect_secrets

    resultat = sonde_detect_secrets()
    assert resultat["positive"] == "POSITIVE_PROBE_DETECTED"
    assert resultat["negative"] == "NEGATIVE_PROBE_ACCEPTED"
    assert resultat["positive_rules"], "la sentinelle a été détectée sans règle nommée"


def test_the_probe_sentinel_is_never_written_in_the_repository():
    """Une valeur ayant la forme d'un secret actif n'entre pas dans le dépôt."""
    from scripts.g0_secret_gate import SENTINELLE_SONDE

    source = _lire(REPO_ROOT / "scripts" / "g0_secret_gate.py")
    assert SENTINELLE_SONDE not in source, (
        "la sentinelle est écrite en clair : elle doit rester assemblée à l'exécution"
    )
    assert SENTINELLE_SONDE not in _lire(Path(__file__))


def test_the_scan_reads_files_as_utf8_whatever_the_platform(tmp_path):
    """Une mesure qui depend de la machine qui la produit n'est pas une mesure.

    `detect-secrets` ouvre les fichiers avec l'encodage de la locale. Sous
    Windows c'est `cp1252`, et un fichier UTF-8 portant un octet invalide dans
    cette table y provoque une `UnicodeDecodeError` que l'outil AVALE : le
    fichier n'est pas scanne, et rien ne le signale. La premiere mesure du lot B
    sous-comptait ainsi 59 detections sur 229, et c'est la CI Linux qui l'a
    montre.

    Le fichier ci-dessous porte U+0081, dont l'encodage UTF-8 (C2 81) est
    indecodable en cp1252, et une affectation de mot de passe litterale. Sans
    forcage de l'UTF-8, il ressort a zero detection sous Windows.
    """
    from scripts.g0_secret_gate import scanner_arbre

    (tmp_path / "piege.py").write_text(
        'ENTETE = ""' + chr(10) + 'password = "MotDePasseLitteral123"' + chr(10),
        encoding="utf-8",
    )
    detections, _ = scanner_arbre(["piege.py"], racine=tmp_path)
    assert detections, (
        "le fichier UTF-8 n'a pas ete scanne : la mesure differerait entre Windows et Linux"
    )


def test_the_gate_refuses_a_detection_without_written_coverage():
    """Une barrière qui accepte l'inconnu n'est pas une barrière."""
    from scripts.g0_secret_gate import confronter

    inconnue = {
        "scanner": "detect-secrets",
        "path": "app/inconnu.py",
        "rule": "Secret Keyword",
        "fingerprint": "0" * 40,
    }
    resultat = confronter([inconnue], set(), {"exceptions": []})
    assert resultat["residus"] == [inconnue]
    assert resultat["couvertes"] == []


def test_the_gate_accepts_what_the_register_covers():
    from scripts.g0_secret_gate import confronter

    connue = {
        "scanner": "detect-secrets",
        "path": "tests/test_api.py",
        "rule": "Secret Keyword",
        "fingerprint": "1" * 40,
    }
    resultat = confronter([connue], set(), {"exceptions": [dict(connue)]})
    assert resultat["residus"] == []
    assert resultat["couvertes"][0]["source"] == "registre"


def test_the_gate_normalises_the_windows_paths_of_the_baseline():
    """Sans normalisation, aucune entrée de la baseline ne s'applique sous Linux."""
    from scripts.g0_secret_gate import charger_baseline

    connues, non_posix = charger_baseline()
    assert non_posix, "aucun chemin normalisé : le constat ne tient plus"
    assert all("\\" not in chemin for chemin, _, _ in connues)


def test_the_gate_covers_the_whole_tracked_tree():
    """Le registre versionné couvre l'arbre d'aujourd'hui, sinon la CI est rouge."""
    from scripts.g0_secret_gate import (
        charger_baseline,
        charger_registre,
        confronter,
        fichiers_a_scanner,
        scanner_arbre,
    )

    connues, _ = charger_baseline()
    detections, rapport = scanner_arbre(fichiers_a_scanner(None))
    assert rapport["complete"], rapport["scan_errors"]
    resultat = confronter(detections, connues, charger_registre())
    assert resultat["residus"] == [], (
        f"{len(resultat['residus'])} détection(s) sans couverture écrite — "
        "qualifier chaque emplacement dans docs/governance/SECRET_SCAN_EXCEPTIONS.json"
    )


def test_the_exception_register_is_documented_entry_by_entry():
    """Empreinte, chemin, commit et justification : les quatre, pour chacune."""
    from scripts.g0_secret_gate import REGISTRE

    registre = json.loads(_lire(REGISTRE))
    assert registre["exceptions"], "registre vide"
    for entree in registre["exceptions"]:
        for champ in ("path", "rule", "fingerprint", "commit", "justification", "family"):
            assert str(entree.get(champ, "")).strip(), f"{entree.get('path')} : « {champ} » vide"
        assert entree["family"] != "NON_REVU", (
            f"{entree['path']} n'appartient à aucune famille revue : "
            "un humain doit trancher avant que la barrière l'accepte"
        )
    assert registre["totals"]["unreviewed"] == 0


def test_the_exception_register_carries_no_value():
    """Un registre d'exceptions qui recopierait les valeurs serait le pire endroit."""
    from scripts.g0_secret_gate import REGISTRE

    registre = json.loads(_lire(REGISTRE))
    for entree in registre["exceptions"]:
        assert "secret" not in {c.lower() for c in entree if c != "rule"}
        assert "value" not in entree
        assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{7,40}|arbre-courant", entree["fingerprint"]), (
            f"empreinte de forme inattendue : {entree['path']}"
        )


# ── la CI applique réellement la barrière ───────────────────────────────────


def test_the_secret_scan_is_no_longer_advisory(workflow):
    """`continue-on-error` sur un scan de secrets, c'est un scan décoratif."""
    etapes = workflow["jobs"]["test"]["steps"]
    scan = [e for e in etapes if "secret scan" in str(e.get("name", "")).lower()]
    assert scan, "aucune étape de scan de secrets dans le job `test`"
    for etape in scan:
        assert not etape.get("continue-on-error"), "le scan de secrets est redevenu consultatif"


def test_the_security_job_exists_and_fetches_the_whole_history(workflow):
    """Un scan d'historique sur un clone superficiel ne voit qu'un commit."""
    job = workflow["jobs"]["g0-security"]
    assert job["name"] == "G0 — Security baseline and secret scan"
    checkout = next(e for e in job["steps"] if "checkout" in str(e.get("uses", "")))
    assert checkout["with"]["fetch-depth"] == 0


def test_the_history_scanner_is_pinned_by_version_and_checksum(workflow):
    """`latest` changerait le jeu de règles sans qu'aucun commit ne l'indique."""
    env = workflow["jobs"]["g0-security"]["env"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", env["GITLEAKS_VERSION"]), "version non épinglée"
    assert env["GITLEAKS_VERSION"] != "latest"
    assert re.fullmatch(r"[0-9a-f]{64}", env["GITLEAKS_SHA256"]), "empreinte SHA-256 absente"
    etapes = " ".join(str(e.get("run", "")) for e in workflow["jobs"]["g0-security"]["steps"])
    assert "sha256sum --check --strict" in etapes, "l'archive n'est pas vérifiée"
    assert "latest" not in etapes.replace("--latest", "")


def test_the_security_job_scans_the_tree_then_the_history(workflow):
    etapes = " ".join(str(e.get("run", "")) for e in workflow["jobs"]["g0-security"]["steps"])
    assert "gitleaks-arbre.json" in etapes
    assert "gitleaks-historique.json" in etapes
    assert '--log-opts="--all"' in etapes


def test_the_security_job_runs_both_probes(workflow):
    etapes = " ".join(str(e.get("run", "")) for e in workflow["jobs"]["g0-security"]["steps"])
    assert "--gitleaks-probe-positive" in etapes
    assert "--gitleaks-probe-negative" in etapes
    assert "--probes" in etapes


def test_the_security_job_publishes_only_redacted_reports(workflow):
    """Les rapports bruts de Gitleaks portent auteur, courriel et message de commit."""
    publication = next(
        e
        for e in workflow["jobs"]["g0-security"]["steps"]
        if "upload-artifact" in str(e.get("uses", ""))
    )
    chemins = publication["with"]["path"]
    assert "gitleaks-arbre.json" not in chemins
    assert "gitleaks-historique.json" not in chemins
    assert "secret-gate-report.json" in chemins


# ── ni donnée réelle, ni secret dans les artefacts ──────────────────────────

_MOTIFS_INTERDITS = (
    re.compile(r"(?i)\b(password|passwd|mot_de_passe)\b\s*[=:]\s*\S{6,}"),
    re.compile(r"(?i)\b(secret_key|secret|api[_-]?key|access[_-]?token|bearer)\b\s*[=:]\s*\S{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\."),
)


def _valeurs_texte(noeud):
    """Toutes les chaînes d'un document JSON, quelle que soit leur profondeur.

    Balayer le fichier brut ne suffit pas : dans du JSON, un guillemet interne
    est échappé et une expression régulière appliquée au texte brut le manque —
    ce qui donne un test rassurant et aveugle.
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


@pytest.mark.parametrize("artefact", ARTEFACTS_LOT_B)
def test_no_secret_or_real_data_in_the_artifacts(artefact):
    document = json.loads(_lire(ARTEFACTS / f"{artefact}.json"))
    for texte in _valeurs_texte(document):
        for motif in _MOTIFS_INTERDITS:
            trouve = motif.search(texte)
            assert not trouve, f"{artefact}.json : {trouve.group(0)[:60]}"


@pytest.mark.parametrize("artefact", ARTEFACTS_LOT_B)
def test_the_artifacts_describe_structure_and_never_content(artefact):
    document = json.loads(_lire(ARTEFACTS / f"{artefact}.json"))
    for cle in _valeurs_texte(document):
        assert cle not in ("rows", "sample_rows", "row_count", "data"), (
            f"{artefact}.json expose un contenu de table : {cle}"
        )


def test_the_generator_uses_synthetic_data_only():
    source = _lire(REPO_ROOT / "scripts" / "g0_security_baseline.py")
    assert "Aucune donnée patient réelle. Aucun secret. Aucun appel réseau." in source
    assert "synth" in source.lower()


# ── documentation cohérente ─────────────────────────────────────────────────


@pytest.mark.parametrize("document", DOCUMENTS_LOT_B)
def test_the_lot_b_documents_exist(document):
    assert (DOCS / document).is_file(), f"document du lot B absent : {document}"


@pytest.mark.parametrize("document", DOCUMENTS_LOT_B)
def test_the_documents_carry_the_classification_banner(document):
    aplati = _aplati(DOCS / document)
    assert "INTERNAL — SECURITY ARCHITECTURE" in aplati
    assert "BASELINE TECHNIQUE — NOT FOR OPERATIONAL DEPLOYMENT" in aplati


@pytest.mark.parametrize("document", DOCUMENTS_LOT_B)
def test_the_banner_does_not_pretend_to_be_a_control(document):
    """Un bandeau n'empêche personne de lire : le dire évite de s'y fier."""
    aplati = _aplati(DOCS / document)
    assert "mention de classification, pas un contrôle d'accès" in aplati
    assert "Le seul contrôle réel serait la visibilité du dépôt" in aplati


@pytest.mark.parametrize("document", DOCUMENTS_LOT_B)
def test_no_real_site_address_in_the_documents(document):
    """Une adresse réelle transformerait une baseline publique en cartographie."""
    texte = _lire(DOCS / document)
    for motif in (
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b"),
    ):
        for trouve in motif.findall(texte):
            assert trouve.startswith(("127.", "0.0.0.0", "10.", "192.168.")), (
                f"{document} : adresse potentiellement réelle — {trouve}"
            )


def test_local_markdown_links_resolve():
    """Un lien mort dans une preuve rend la preuve invérifiable."""
    casses = []
    for document in sorted(DOCS.glob("*.md")):
        for cible in re.findall(r"\]\((?!https?://)([^)#]+)", _lire(document)):
            if not (document.parent / cible).resolve().exists():
                casses.append(f"{document.name} -> {cible}")
    assert not casses, f"liens locaux cassés : {casses}"


def test_the_documents_transmit_findings_and_do_not_fix_them():
    """Le lot B photographie et qualifie ; la remédiation appartient au lot D."""
    for document in DOCUMENTS_LOT_B:
        aplati = _aplati(DOCS / document)
        assert "lot D" in aplati, f"{document} ne dit pas à qui la remédiation revient"


def test_no_go_verdict_is_ever_pronounced():
    """Prononcer un GO ici usurperait une décision qui n'appartient pas au lot B.

    La comparaison porte sur des **jetons entiers**, jamais sur des
    sous-chaînes. `CSA_SITE_PRODUCTION_GO_BLOCKER` contient littéralement
    `SITE_PRODUCTION_GO` tout en disant l'inverse : c'est un marqueur de
    blocage. Un garde-fou qui refuse le mot qui interdit, parce qu'il ressemble
    au mot qui autorise, pousse à retirer le blocage pour faire passer le test.
    """
    interdits = {"G0_PASS", "REAL_DATA_GO", "SITE_PRODUCTION_GO", "DISTRIBUTION_GO"}
    for document in DOCUMENTS_LOT_B:
        jetons = set(re.findall(r"[A-Z][A-Z0-9_]{3,}", _lire(DOCS / document)))
        prononces = jetons & interdits
        assert not prononces, f"{document} prononce {sorted(prononces)}"


# ── invariants de gouvernance ───────────────────────────────────────────────


def test_governance_statuses_are_unchanged():
    assert (GOUVERNANCE / "CLINICAL_STATUS").read_text(encoding="utf-8").strip() == (
        "REAL_DATA_NO_GO"
    )
    assert (GOUVERNANCE / "DISTRIBUTION_STATUS").read_text(encoding="utf-8").strip() == (
        "DISTRIBUTION_NO_GO"
    )
    config = _lire(REPO_ROOT / "app" / "core" / "config.py")
    for reglage in (
        "CSA_SYNC_ENABLED: bool = False",
        "ENABLE_DH36_LISTENER: bool = False",
        "ANALYZER_RAW_LISTENER_ENABLED: bool = False",
    ):
        assert reglage in config, f"réglage modifié : {reglage}"


def test_the_branch_protection_status_is_still_required():
    """Le marqueur disparaîtrait si l'on prétendait la règle déjà appliquée."""
    document = _lire(GOUVERNANCE / "BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md")
    assert "BRANCH_PROTECTION_UPDATE_REQUIRED" in document


def test_the_branch_protection_document_records_the_state_actually_read():
    """Un état cible sans état constaté ne permet aucune décision."""
    aplati = _aplati(GOUVERNANCE / "BRANCH_PROTECTION_PRE_TAG_REQUIRED_CHECKS.md")
    assert "G0 — Security baseline and secret scan" in aplati
    assert "strict" in aplati
    assert "enforce_admins" in aplati


# ── provenance ──────────────────────────────────────────────────────────────


def test_the_security_provenance_separates_what_is_compared_from_what_varies():
    entete = json.loads(_lire(ARTEFACTS / "security-provenance.json"))
    assert set(entete["deterministic"]) >= {
        "relevant_input_set",
        "relevant_input_tree_sha256",
        "relevant_input_file_count",
        "baseline_input_commit",
    }
    assert set(entete["volatile"]) == {"generated_at", "platform", "python_version"}


def test_the_security_provenance_never_cites_a_temporary_reference():
    entete = json.loads(_lire(ARTEFACTS / "security-provenance.json"))
    reference = entete["deterministic"]["baseline_input_ref"]
    assert not reference.startswith(("tmp/", "wip/", "g0/")), (
        f"provenance ancrée sur une référence appelée à disparaître : {reference}"
    )


def test_the_security_input_set_does_not_include_the_lot_b_artifacts():
    """Un motif large rendrait l'empreinte auto-référentielle, donc toujours fausse."""
    from scripts.g0_provenance import ENSEMBLES_ENTREE

    motifs = ENSEMBLES_ENTREE["security"]
    assert "artifacts/g0/*" not in motifs
    assert "artifacts/g0/**/*" not in motifs
    for artefact in ARTEFACTS_LOT_B:
        assert f"artifacts/g0/{artefact}.json" not in motifs


def test_the_input_order_is_the_posix_string_order(tmp_path, monkeypatch):
    """Sur un arbre où les deux tris DIVERGENT — sinon le test est aveugle.

    Première rédaction : « l'ordre obtenu est trié ». Une mutation remplaçant
    `sorted(trouves, key=chemin_relatif)` par `sorted(trouves)` **passait**,
    parce que sur les ensembles réels du dépôt les deux tris coïncident. Un test
    qui ne distingue pas les deux ne prouve rien.

    Ici, `Beta.py` / `Zebra.py` / `alpha.py` séparent les deux ordres : la
    comparaison de `Path` replie la casse sous Windows et donnerait
    alpha, Beta, Zebra ; la chaîne POSIX donne Beta, Zebra, alpha.
    """
    import scripts.g0_provenance as provenance_module

    depot = tmp_path / "depot"
    (depot / "app").mkdir(parents=True)
    for nom in ("Zebra.py", "alpha.py", "Beta.py"):
        (depot / "app" / nom).write_text("x" + chr(10), encoding="utf-8")
    monkeypatch.setattr(provenance_module, "RACINE", depot)
    monkeypatch.setitem(provenance_module.ENSEMBLES_ENTREE, "security", ("app/**/*",))

    relatifs = [
        provenance_module.chemin_relatif(c) for c in provenance_module.fichiers_entree("security")
    ]
    assert relatifs == ["app/Beta.py", "app/Zebra.py", "app/alpha.py"], (
        "l'ordre n'est pas celui des chaînes POSIX : l'empreinte différerait "
        f"entre Windows et Linux — obtenu {relatifs}"
    )


def test_the_input_order_does_not_depend_on_the_platform():
    """C'est le défaut exact qui a fait échouer le lot A en CI."""
    from scripts.g0_provenance import chemin_relatif, fichiers_entree

    fichiers = fichiers_entree("security")
    relatifs = [chemin_relatif(c) for c in fichiers]
    assert relatifs == sorted(relatifs), (
        "l'ordre des entrées n'est pas celui des chaînes POSIX : "
        "l'empreinte différerait entre Windows et Linux"
    )


# ════════════════════════════════════════════════════════════════════════════
# Amendement après revue indépendante — G0_LOT_B_REVIEW = CHANGES_REQUIRED
#
# La revue a relevé quatre défauts d'outillage, dont deux qui privaient la
# barrière de son effet. Chaque correction est verrouillée ici, et chaque
# verrou est vérifié par mutation : on casse volontairement l'objet contrôlé et
# on exige que le contrôle échoue. Un test qui reste vert sur une mutation est
# aveugle, et vaut moins que pas de test — il donne confiance sans raison.
# ════════════════════════════════════════════════════════════════════════════


def _finding_gitleaks(**surcharges):
    """Un finding Gitleaks minimal, à la forme réelle des rapports."""
    finding = {
        "File": "docs/exemple.md",
        "RuleID": "generic-api-key",
        "Commit": "a" * 40,
        "StartLine": 12,
        "Fingerprint": f"{'a' * 40}:docs/exemple.md:generic-api-key:12",
    }
    finding.update(surcharges)
    return finding


def _ecrire_rapport(chemin, findings):
    chemin.write_text(json.dumps(findings), encoding="utf-8")
    return chemin


# ── §3 — l'identité d'une détection Gitleaks est son Fingerprint ────────────


def test_a_gitleaks_finding_is_identified_by_its_fingerprint(tmp_path):
    """Le champ `Fingerprint` est lu tel quel, jamais remplacé.

    La version précédente inscrivait le SHA du COMMIT — ou la chaîne littérale
    `arbre-courant` — dans le champ `fingerprint`. Ce n'est pas une identité :
    deux valeurs différentes introduites par le même commit la partageaient.
    """
    from scripts.g0_secret_gate import lire_rapport_gitleaks

    rapport = _ecrire_rapport(tmp_path / "gl.json", [_finding_gitleaks()])
    detections = lire_rapport_gitleaks(rapport, "historique")

    assert len(detections) == 1
    detection = detections[0]
    assert detection["fingerprint"] == f"{'a' * 40}:docs/exemple.md:generic-api-key:12"
    assert detection["commit"] == "a" * 40
    assert detection["start_line"] == 12
    assert detection["scope"] == "history"
    assert detection["fingerprint"] != detection["commit"], (
        "le commit a de nouveau été inscrit à la place de l'empreinte"
    )
    assert "arbre-courant" not in detection["fingerprint"]


def test_a_gitleaks_finding_without_a_fingerprint_is_refused(tmp_path):
    """MUTATION — `Fingerprint` absent : GITLEAKS_FINDING_WITHOUT_FINGERPRINT."""
    from scripts.g0_secret_gate import DetectionSansEmpreinte, lire_rapport_gitleaks

    for absent in ({}, {"Fingerprint": ""}, {"Fingerprint": "   "}):
        finding = _finding_gitleaks(**absent) if absent else _finding_gitleaks()
        if not absent:
            finding.pop("Fingerprint")
        rapport = _ecrire_rapport(tmp_path / "gl.json", [finding])
        with pytest.raises(DetectionSansEmpreinte, match="GITLEAKS_FINDING_WITHOUT_FINGERPRINT"):
            lire_rapport_gitleaks(rapport, "historique")


def test_the_acceptance_key_of_a_gitleaks_detection_carries_its_fingerprint():
    """Aucune clé ne se réduit à `chemin + règle`."""
    from scripts.g0_secret_gate import _cle

    detection = {
        "scanner": "gitleaks-historique",
        "path": "docs/exemple.md",
        "rule": "generic-api-key",
        "fingerprint": "empreinte-exacte-1",
    }
    autre = {**detection, "fingerprint": "empreinte-exacte-2"}
    assert _cle(detection) != _cle(autre), (
        "deux identités différentes partagent la même clé d'acceptation — "
        "c'est exactement le défaut que la revue a démontré"
    )
    assert "empreinte-exacte-1" in _cle(detection)


def test_a_detection_without_fingerprint_cannot_be_keyed():
    from scripts.g0_secret_gate import DetectionSansEmpreinte, _cle

    with pytest.raises(DetectionSansEmpreinte):
        _cle({"scanner": "gitleaks-arbre", "path": "a", "rule": "b", "fingerprint": ""})


@pytest.mark.parametrize(
    ("mutation", "attendu"),
    [
        ({}, True),
        ({"fingerprint": "identite-differente"}, False),
        ({"rule": "aws-access-token"}, False),
        ({"path": "docs/autre.md"}, False),
    ],
    ids=[
        "identite-exacte-acceptee",
        "meme-chemin-meme-regle-AUTRE-empreinte-refusee",
        "meme-chemin-NOUVELLE-regle-refusee",
        "NOUVEAU-chemin-refuse",
    ],
)
def test_only_the_exact_qualified_identity_is_accepted(mutation, attendu):
    """MUTATION centrale de la revue.

    Un chemin et une règle déjà inscrits ne doivent pas absorber une seconde
    valeur détectable. C'est ce que faisait la version précédente, et c'est le
    scénario par lequel un vrai secret aurait pu entrer sans être relu.
    """
    from scripts.g0_secret_gate import confronter

    qualifiee = {
        "scanner": "gitleaks-historique",
        "path": "docs/exemple.md",
        "rule": "generic-api-key",
        "fingerprint": "empreinte-qualifiee",
    }
    registre = {"exceptions": [{**qualifiee, "family": "documentation", "justification": "x" * 40}]}
    detection = {**qualifiee, **mutation}

    resultat = confronter([detection], set(), registre)
    couverte = not resultat["residus"]
    assert couverte is attendu, (
        f"mutation {mutation or 'aucune'} : couverte={couverte}, attendu={attendu}"
    )


def test_moving_a_finding_to_another_line_creates_a_new_identity(tmp_path):
    """MUTATION — la ligne entre dans l'empreinte Gitleaks.

    Déplacer une valeur détectée est un fait nouveau : la qualification
    précédente portait sur un emplacement, pas sur un fichier entier.
    """
    from scripts.g0_secret_gate import _cle, lire_rapport_gitleaks

    avant = _ecrire_rapport(tmp_path / "a.json", [_finding_gitleaks()])
    apres = _ecrire_rapport(
        tmp_path / "b.json",
        [
            _finding_gitleaks(
                StartLine=99,
                Fingerprint=f"{'a' * 40}:docs/exemple.md:generic-api-key:99",
            )
        ],
    )
    assert _cle(lire_rapport_gitleaks(avant, "historique")[0]) != _cle(
        lire_rapport_gitleaks(apres, "historique")[0]
    )


def test_no_detected_value_ever_crosses_the_reader(tmp_path):
    """`Secret` et `Match` ne franchissent jamais la lecture du rapport."""
    from scripts.g0_secret_gate import lire_rapport_gitleaks

    rapport = _ecrire_rapport(
        tmp_path / "gl.json",
        [_finding_gitleaks(Secret="valeur-detectee", Match="ligne=valeur-detectee")],
    )
    detections = lire_rapport_gitleaks(rapport, "arbre")
    aplati = json.dumps(detections)
    assert "valeur-detectee" not in aplati
    assert not {"Secret", "Match", "secret", "match"} & set(detections[0])


# ── §4 — un fichier illisible n'est pas un fichier propre ───────────────────


def test_the_tree_scan_accounts_for_every_file(tmp_path):
    """Chaque fichier tombe dans exactement une catégorie."""
    from scripts.g0_secret_gate import scanner_arbre

    (tmp_path / "propre.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
    _, rapport = scanner_arbre(["propre.py", "image.png"], racine=tmp_path)

    assert rapport["attempted_files"] == 2
    assert rapport["successfully_scanned_files"] == 1
    assert rapport["explicitly_excluded_files"] == 1
    assert rapport["scan_errors"] == []
    assert rapport["complete"] is True


@pytest.mark.parametrize(
    ("exception", "motif"),
    [
        (OSError("disque"), "OS_ERROR"),
        (PermissionError("refusé"), "PERMISSION_DENIED"),
        (UnicodeDecodeError("utf-8", b"", 0, 1, "invalide"), "DECODE_ERROR"),
        (RuntimeError("le scanner a explosé"), "SCANNER_ERROR"),
    ],
    ids=["os-error", "permission-refusee", "decodage-impossible", "scanner-en-echec"],
)
def test_any_read_error_makes_the_scan_incomplete(tmp_path, monkeypatch, exception, motif):
    """MUTATION — une erreur de lecture ne doit jamais ressembler à un fichier propre.

    La version précédente faisait `except (OSError, UnicodeDecodeError): continue`.
    Un fichier illisible produisait donc exactement le même résultat qu'un fichier
    sans secret : zéro détection, barrière verte.
    """
    from detect_secrets.core import scan

    import scripts.g0_secret_gate as gate

    (tmp_path / "cible.py").write_text("x = 1\n", encoding="utf-8")

    def exploser(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(scan, "scan_file", exploser)
    _, rapport = gate.scanner_arbre(["cible.py"], racine=tmp_path)

    assert rapport["complete"] is False, "l'erreur de lecture a été avalée"
    assert rapport["successfully_scanned_files"] == 0
    assert [e["reason"] for e in rapport["scan_errors"]][0].startswith(motif)


def test_a_file_that_vanishes_between_inventory_and_read_is_an_error(tmp_path):
    """MUTATION — un fichier suivi mais absent au moment de la lecture."""
    from scripts.g0_secret_gate import scanner_arbre

    _, rapport = scanner_arbre(["jamais-ecrit.py"], racine=tmp_path)
    assert rapport["complete"] is False
    assert rapport["scan_errors"][0]["reason"] == "FILE_MISSING_AT_READ_TIME"


def test_binary_exclusions_are_explicit_versioned_and_counted():
    """Une exclusion implicite est une exclusion que personne ne relit."""
    from scripts.g0_secret_gate import SUFFIXES_EXCLUS, exclu_du_scan

    assert SUFFIXES_EXCLUS, "aucune exclusion déclarée"
    for suffixe in SUFFIXES_EXCLUS:
        assert exclu_du_scan(f"quelque/part/fichier{suffixe}")
    assert not exclu_du_scan("app/main.py")


# ── §5 — les deux fichiers exclus du scan sont relus par un validateur ──────


def test_the_governance_files_pass_their_specialised_validator():
    from scripts.g0_secret_gate import valider_fichiers_de_gouvernance

    manquements = valider_fichiers_de_gouvernance()
    assert manquements == [], manquements


@pytest.mark.parametrize(
    ("mutation", "motif"),
    [
        ({"secret": "valeur"}, "champ porteur de valeur"),
        ({"match": "ligne = valeur"}, "champ porteur de valeur"),
        ({"raw": "valeur"}, "champ porteur de valeur"),
        ({"justification": "trop court"}, "justification trop courte"),
        ({"family": "NON_REVU"}, "NON_REVU"),
        ({"fingerprint": "pas-une-empreinte"}, "format invalide"),
        ({"champ_invente": "x"}, "hors schéma"),
        ({"rotation_required": "oui"}, "n'est pas un booléen"),
    ],
    ids=[
        "champ-Secret",
        "champ-Match",
        "champ-Raw",
        "justification-vide-de-sens",
        "famille-non-revue",
        "empreinte-mal-formee",
        "champ-hors-schema",
        "type-invalide",
    ],
)
def test_the_registry_validator_refuses_each_defect(tmp_path, monkeypatch, mutation, motif):
    """MUTATION — le validateur spécialisé refuse ce que le scan ne voit plus."""
    import scripts.g0_secret_gate as gate

    registre = json.loads(gate.REGISTRE.read_text(encoding="utf-8"))
    registre["exceptions"][0].update(mutation)
    faux = tmp_path / "registre.json"
    faux.write_text(json.dumps(registre), encoding="utf-8")
    monkeypatch.setattr(gate, "REGISTRE", faux)

    manquements = gate.valider_fichiers_de_gouvernance()
    assert any(motif in m for m in manquements), (
        f"mutation {mutation} non détectée — manquements : {manquements[:3]}"
    )


def test_the_validator_refuses_a_private_key_in_the_baseline(tmp_path, monkeypatch):
    """MUTATION — un bloc PEM dans `.secrets.baseline`.

    Le fichier est soustrait aux règles d'entropie pour éviter une récursion
    d'empreintes, et pour cette seule raison. Sans validateur, il deviendrait
    l'endroit du dépôt où l'on peut écrire n'importe quoi.
    """
    import scripts.g0_secret_gate as gate

    faux = tmp_path / "baseline.json"
    faux.write_text(
        json.dumps({"note": gate.SENTINELLE_PEM_DEBUT + "\nAAAA\n" + gate.SENTINELLE_PEM_FIN}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "BASELINE", faux)
    assert any("CLE_PRIVEE_PEM" in m for m in gate.valider_fichiers_de_gouvernance())


def test_the_validator_does_not_exempt_a_file_because_it_lives_in_docs(tmp_path, monkeypatch):
    """Un chemin ne rend pas un contenu inoffensif."""
    import scripts.g0_secret_gate as gate

    assert (
        str(gate.REGISTRE)
        .replace("\\", "/")
        .endswith("docs/governance/SECRET_SCAN_EXCEPTIONS.json")
    )
    registre = json.loads(gate.REGISTRE.read_text(encoding="utf-8"))
    registre["exceptions"][0]["justification"] = (
        "Contient une adresse copiee d'un rapport : personne@exemple.test, ce qui ne "
        "doit jamais arriver dans ce fichier."
    )
    faux = tmp_path / "r.json"
    faux.write_text(json.dumps(registre), encoding="utf-8")
    monkeypatch.setattr(gate, "REGISTRE", faux)
    assert any("ADRESSE_ELECTRONIQUE" in m for m in gate.valider_fichiers_de_gouvernance())


# ── §6 — la couverture de l'historique est réconciliée, pas affirmée ────────


def test_the_history_scan_is_reconciled_against_the_repository():
    """Un scan dont on ne sait pas sur quoi il a porté ne prouve rien."""
    from scripts.g0_secret_gate import reconcilier_historique

    comptes = {
        "reachable_commits": 458,
        "merge_commits": 77,
        "non_merge_commits": 381,
        "empty_or_non_diff_commits": 0,
        "is_shallow_repository": False,
        "scan_command": "gitleaks git . --log-opts=--all",
        "log_opts": "rev-list --all ; --merges ; --no-merges",
    }
    bilan = reconcilier_historique([], comptes)
    for champ in (
        "reachable_commits",
        "merge_commits",
        "non_merge_commits",
        "empty_or_non_diff_commits",
        "gitleaks_expected_commits_scanned",
        "distinct_commits_present_in_findings",
        "scan_command",
        "log_opts",
        "is_shallow_repository",
    ):
        assert champ in bilan, f"compteur absent : {champ}"
    assert bilan["reachable_commits"] == bilan["merge_commits"] + bilan["non_merge_commits"], (
        "l'addition ne tombe pas juste : l'écart doit être expliqué, pas ignoré"
    )
    assert bilan["status"] == "HISTORY_SCAN_COUNT_RECONCILED"


@pytest.mark.parametrize(
    "comptes",
    [
        {
            "reachable_commits": 458,
            "merge_commits": 77,
            "non_merge_commits": 381,
            "is_shallow_repository": True,
        },
        {
            "reachable_commits": 445,
            "merge_commits": 77,
            "non_merge_commits": 367,
            "is_shallow_repository": False,
        },
        {},
    ],
    ids=["clone-superficiel", "addition-qui-ne-tombe-pas-juste", "comptages-absents"],
)
def test_an_unreconciled_history_cannot_claim_coverage(comptes):
    """MUTATION — trois façons de ne pas savoir sur quoi le scan a porté.

    Le second cas est exactement celui du rapport précédent : 445 annoncés,
    367 parcourus, 78 d'écart, aucune explication. La barrière refuse
    désormais de prononcer la couverture de l'historique dans ce cas.
    """
    from scripts.g0_secret_gate import reconcilier_historique

    bilan = reconcilier_historique([], comptes)
    assert bilan["reconciled"] is False
    assert bilan["status"] == "HISTORY_SCAN_COUNT_UNRECONCILED"


def test_the_history_probe_removes_its_sentinel_before_scanning():
    """La sonde doit prouver que l'HISTORIQUE est lu, pas seulement l'arbre.

    Le dépôt jetable ajoute la sentinelle, puis la retire : à HEAD, l'arbre est
    propre. Une sonde positive qui réussit ne peut donc réussir que par
    l'historique.
    """
    workflow = _lire(REPO_ROOT / ".github" / "workflows" / "ci.yml")
    etape = workflow.split("Non-emptiness probes on a throwaway git repository", 1)[1][:2000]
    assert 'git -C "$sonde" rm -q porteur.txt' in etape, (
        "la sentinelle n'est pas retirée : la sonde ne distingue plus arbre et historique"
    )
    assert 'gitleaks" git "$sonde"' in etape or "gitleaks git" in etape


# ── §7 — la portée de la matrice, énoncée en chiffres ───────────────────────


def test_the_matrix_states_what_it_proves_and_on_how_many_operations():
    matrice = _payload("rbac-matrix")
    portee = matrice["scope"]
    assert portee["operations_statically_classified"] == 231
    assert portee["operations_unresolved_statically"] == 0
    assert portee["operations_runtime_probed"] < portee["operations_statically_classified"]
    assert (
        portee["operations_runtime_probed"] + portee["operations_not_runtime_probed"]
        == portee["operations_statically_classified"]
    )


def test_a_probe_is_not_an_operation():
    """99 sondes portent sur 65 opérations : confondre les deux gonflerait d'un tiers."""
    portee = _payload("rbac-matrix")["scope"]
    assert portee["probes_executed"] > portee["operations_runtime_probed"], (
        "sondes et opérations distinctes ne sont plus distinguées"
    )
    assert portee["probes_authorization_reached"] >= portee["operations_authorization_reached"]


def test_zero_unresolved_never_reads_as_runtime_confirmed():
    """MUTATION de rédaction — la confusion que la revue a relevée.

    `UNRESOLVED = 0` porte sur la classification statique. Écrit sans cette
    précision, il laisse croire que les 231 opérations ont été exercées.
    """
    aplati = _aplati(DOCS / "RBAC.md")
    assert "classification statique" in aplati.lower()
    for interdit in (
        "les 231 opérations ont été exercées",
        "231 opérations testées dynamiquement",
        "les 231 opérations ont été sondées",
        "toutes les opérations ont été exercées",
    ):
        assert interdit.lower() not in aplati.lower(), f"affirmation fausse : « {interdit} »"
    assert "non exercée" in aplati.lower() or "non sondée" in aplati.lower(), (
        "le document ne dit nulle part combien d'opérations n'ont PAS été exercées"
    )


def test_the_document_publishes_the_six_scope_counters():
    aplati = _aplati(DOCS / "RBAC.md")
    portee = _payload("rbac-matrix")["scope"]
    for champ in (
        "operations_statically_classified",
        "operations_runtime_probed",
        "operations_authorization_reached",
        "operations_validation_stopped_before_authorization",
        "operations_not_runtime_probed",
        "operations_unresolved_statically",
    ):
        assert str(portee[champ]) in aplati, f"valeur de {champ} absente de RBAC.md"


# ── §8 — les blocages de site sont formalisés, pas corrigés ─────────────────


def _constat(identifiant):
    for constat in _payload("rbac-matrix")["findings"]:
        if constat["id"] == identifiant:
            return constat
    raise AssertionError(f"constat absent : {identifiant}")


def test_the_environment_template_finding_is_recorded():
    """B-12 — MUTATION : sa disparition doit faire échouer ce test."""
    constat = _constat("B-12")
    assert constat["classement"] == "P1"
    assert "CSA_SITE_PRODUCTION_GO_BLOCKER" in constat["marqueurs"]
    assert "DEPLOYMENT_TEMPLATE_FAIL_CLOSED_REQUIRED" in constat["marqueurs"]
    cite = " ".join(constat["preuve"])
    for reglage in (
        "ANALYZER_RAW_LISTENER_ENABLED",
        "ANALYZER_HEMATOLOGY_ENABLED",
        "ANALYZER_BIOCHEMISTRY_ENABLED",
        "ANALYZER_IMMUNO_ENABLED",
    ):
        assert reglage in cite, f"réglage non cité dans la preuve : {reglage}"


def test_the_environment_template_is_not_modified_by_this_lot():
    """Le constat B-12 vaut PARCE QUE le fichier n'a pas été touché.

    Le corriger ici rendrait la preuve invérifiable : on ne saurait plus si le
    défaut a existé.
    """
    modele = REPO_ROOT / ".env.example"
    if not modele.is_file():
        pytest.skip(".env.example absent de cette arborescence")
    contenu = modele.read_text(encoding="utf-8")
    assert "ANALYZER_RAW_LISTENER_ENABLED=true" in contenu, (
        "le lot B a corrigé .env.example — hors périmètre, et cela invalide B-12"
    )


def test_the_report_verification_token_finding_is_fully_qualified():
    """B-03 — MUTATION : la perte d'un attribut doit faire échouer ce test."""
    constat = _constat("B-03")
    assert "CSA_SITE_PRODUCTION_GO_BLOCKER" in constat["marqueurs"]
    assert "REPORT_VERIFICATION_TOKEN_HARDENING_REQUIRED" in constat["marqueurs"]
    attributs = constat["attributs"]
    assert attributs["facteur_unique"] is True
    assert attributs["expiration"] == "aucune"
    assert attributs["rejouable"] is True
    assert attributs["journalise_en_clair"] is True
    assert attributs["revocable_independamment_du_compte_rendu"] is False


def test_the_three_segregation_gaps_are_kept_and_detailed():
    """B-08 — MUTATION : la disparition d'un écart doit faire échouer ce test."""
    constat = _constat("B-08")
    assert "SEGREGATION_OF_DUTIES_DECISION_REQUIRED" in constat["marqueurs"]
    operations = {e["operation"] for e in constat["ecarts"]}
    assert operations == {
        "POST /api/v1/aes",
        "POST /api/v1/quality/non-conformities",
        "POST /api/v1/billing/calculate",
    }, operations
    for ecart in constat["ecarts"]:
        for champ in ("attendu", "observe", "capacite_obtenue", "decision_metier_requise"):
            assert ecart[champ], f"{ecart['operation']} : {champ} vide"
        assert "distincte" in ecart["correction"]


def test_every_site_blocker_is_listed_in_the_findings_document():
    aplati = _aplati(DOCS / "SECURITY_FINDINGS.md")
    for identifiant in ("B-03", "B-08", "B-12"):
        assert identifiant in aplati, f"{identifiant} absent de SECURITY_FINDINGS.md"
    assert "CSA_SITE_PRODUCTION_GO_BLOCKER" in aplati


# ── §10 — la barrière ne peut pas redevenir décorative ──────────────────────


def test_the_secret_scan_never_returns_to_advisory():
    """MUTATION — le retour de `continue-on-error` sur le scan de secrets."""
    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "ci.yml"))
    bloc = json.dumps(workflow["jobs"]["g0-security"])
    assert "continue-on-error" not in bloc, (
        "un pas du job de sécurité est redevenu consultatif — c'est-à-dire décoratif"
    )


def test_the_security_job_checks_out_the_full_history():
    """MUTATION — le retour de `fetch-depth: 1`.

    Sans historique complet, le scan Gitleaks porte sur un seul commit et le
    dit vert.
    """
    workflow = yaml.safe_load(_lire(REPO_ROOT / ".github" / "workflows" / "ci.yml"))
    checkout = next(
        e
        for e in workflow["jobs"]["g0-security"]["steps"]
        if str(e.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout.get("with", {}).get("fetch-depth") == 0, (
        "le job de sécurité ne récupère plus tout l'historique : le scan Gitleaks "
        "porterait sur un seul commit et le dirait vert"
    )

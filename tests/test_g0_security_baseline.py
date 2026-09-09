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
    detections = scanner_arbre(fichiers_a_scanner(None))
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
    """Prononcer un GO ici usurperait une décision qui n'appartient pas au lot B."""
    interdits = ("G0_PASS", "REAL_DATA_GO", "SITE_PRODUCTION_GO", "DISTRIBUTION_GO")
    for document in DOCUMENTS_LOT_B:
        texte = _lire(DOCS / document)
        for mot in interdits:
            assert mot not in texte, f"{document} prononce « {mot} »"


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

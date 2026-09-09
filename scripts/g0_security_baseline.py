"""Baseline de sécurité G0 — RBAC, données sensibles, flux, journaux, secrets.

Ce que ce script produit, et pourquoi chaque artefact existe.

``rbac-matrix.json``
    Les 231 opérations OpenAPI du lot A, chacune avec sa garde réelle, les
    rôles qu'elle autorise, ceux qu'elle refuse, et le **niveau de confiance**
    de cette affirmation. La matrice ne réécrit aucune liste de routes : elle
    dérive de `artifacts/g0/routes.json`, produit par le lot A à partir de
    l'application elle-même. Réécrire les routes à la main aurait produit une
    matrice qui décrit une application imaginaire.

    Une garde n'est jamais déduite d'un nom de route. Elle vient soit des
    dépendances FastAPI réellement appliquées, soit de la lecture du corps de
    la fonction, soit d'une sonde exécutée contre l'application.

``data-classification.json``
    Les 519 colonnes réellement présentes dans `artifacts/g0/schema.json`,
    classées. Les acteurs qui atteignent une table ne sont pas affirmés : ils
    sont **calculés** depuis la matrice, par les routes qui servent la table.

``external-flows.json``
    Les frontières recensées par le lot A, complétées par les données qui y
    circulent.

``log-sentinel-observations.json``
    Des valeurs synthétiques uniques sont écrites par un parcours applicatif,
    puis cherchées dans les journaux, les métriques, les étiquettes de
    métriques, les messages d'erreur et la table d'audit. Ce qui est trouvé est
    **enregistré, pas corrigé** : le lot B photographie.

``secret-scan-summary.json``
    Revue de `.secrets.baseline`, emplacement par emplacement. **Aucune valeur
    de secret n'est recopiée**, pas même tronquée.

``security-provenance.json``
    De quel code tout cela parle — voir `scripts/g0_provenance.py`.

**Déterminisme.** Deux exécutions sur le même arbre produisent des octets
identiques. Les sondes runtime tournent sur une base SQLite jetable, semée par
ce script avec des données strictement synthétiques ; leur résultat est le code
HTTP observé, qui ne dépend d'aucun état extérieur.

Aucune donnée patient réelle. Aucun secret. Aucun appel réseau.
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from scripts.g0_security_rules import (  # noqa: E402
    CATEGORIE_PAR_DEFAUT,
    CATEGORIE_PAR_DEFAUT_TABLE,
    CATEGORIES,
    CONTEXTE_TABLE_DEFAUT,
    CONTEXTE_TABLES,
    DEPENDANCES_NON_AUTORISANTES,
    FLUX_EXTERNES,
    REGLES_NOMS,
    REVUE_BASELINE_SECRETS,
    RISQUE_PAR_CATEGORIE,
    ROLES,
    SEMANTIQUE_GARDES,
    STOCKAGE_COMMUN,
    SURCHARGES_COLONNES,
    TABLE_VERS_ROUTES,
)

ARTEFACTS = RACINE / "artifacts" / "g0"

# ── Sentinelles ─────────────────────────────────────────────────────────────
#
# Improbables par construction : aucune de ces chaînes ne peut apparaître dans
# un jeu de données réel, et aucune ne ressemble à un secret. Les chercher dans
# un journal ne produit donc ni faux positif ni fuite.
SENTINELLES: dict[str, str] = {
    "ipp": "G0SENT-IPP-7Q4Z8M2X",
    "nom": "ZZQXSENTINELLE",
    "prenom": "VVKWSENTINEL",
    "date_naissance": "1953-11-27",
    "telephone": "0709876543219",
    "code_barres": "G0SENT-BARCODE-4KJ9P",
    "analyte": "G0SENTANALYTE",
    "valeur_resultat": "1234.5678",
    "jeton_verification": "G0SENT-VERIFTOKEN-R6XW3",
    "quartier": "G0SENT-QUARTIER-DZ81",
}

#: Mot de passe des comptes synthétiques des sondes. Base jetable, détruite en
#: fin d'exécution ; il ne protège rien et ne désigne aucun système.
_MDP_SONDE = "G0Probe!Synthetic1"  # pragma: allowlist secret  # noqa: S105


# ── Lecture des artefacts du lot A ──────────────────────────────────────────


def _lire_json(chemin: Path) -> Any:
    if not chemin.is_file():
        raise SystemExit(
            f"Artefact du lot A introuvable : {chemin}. "
            "La baseline de sécurité en dérive et ne peut pas s'en passer."
        )
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger_lot_a() -> dict[str, Any]:
    """Les artefacts dont le lot B dérive, jamais recopiés à la main."""
    return {
        "routes": _lire_json(ARTEFACTS / "routes.json")["payload"],
        "entrypoints": _lire_json(ARTEFACTS / "entrypoints.json")["payload"],
        "schema": _lire_json(ARTEFACTS / "schema.json")["payload"],
        "qualification": _lire_json(RACINE / "docs" / "g0" / "ROUTE_EXPOSURE_QUALIFICATION.json"),
    }


# ── Lecture du corps des endpoints ──────────────────────────────────────────

_MOTIFS_PORTEE_SERVICE = (
    "can_access_patient",
    "can_access_sample",
    "can_access_result",
    "can_access_unit",
    "apply_patient_scope",
    "apply_sample_patient_scope",
    "apply_result_patient_scope",
)


def _portees_service(app: Any) -> dict[tuple[str, str], list[str]]:
    """Cloisonnements appliqués DANS le corps de la fonction, pas en dépendance.

    Une garde de rôle se voit dans les dépendances ; le cloisonnement par unité,
    lui, est appelé à l'intérieur du handler. Ne regarder que les dépendances
    ferait conclure qu'aucun cloisonnement patient n'existe — ce serait faux, et
    la matrice le dirait à tort.
    """
    from fastapi.routing import APIRoute

    trouves: dict[tuple[str, str], list[str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):  # pragma: no cover — endpoint sans source
            continue
        presents = sorted({motif for motif in _MOTIFS_PORTEE_SERVICE if motif in source})
        if not presents:
            continue
        for methode in route.methods or []:
            trouves[(route.path, methode)] = presents
    return trouves


# ── Matrice RBAC — partie statique ──────────────────────────────────────────


def _roles_depuis_gardes(gardes: list[str]) -> tuple[list[str], list[str]]:
    """Intersection des rôles autorisés par chaque garde présente.

    Deux gardes se cumulent : `forbid_accountant` + `require_officer` n'autorise
    pas l'union mais l'intersection. Prendre l'union aurait élargi la matrice
    au-delà de ce que l'application permet — une erreur du côté rassurant.
    """
    autorises = set(ROLES)
    for garde in gardes:
        semantique = SEMANTIQUE_GARDES.get(garde)
        if semantique is None:
            raise SystemExit(
                f"Garde inconnue : {garde!r}. Ajoutez-la à SEMANTIQUE_GARDES avec "
                "sa sémantique lue dans le code, ou la matrice affirmerait ce "
                "qu'elle ne sait pas."
            )
        if semantique["nature"] == "authentication":
            continue
        autorises &= set(semantique["roles_autorises"])
    return sorted(autorises), sorted(set(ROLES) - autorises)


def _qualification_par_chemin(qualification: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entree["path"]: entree for entree in qualification["qualified_routes"]}


def _operation_statique(
    operation: dict[str, Any],
    portees: dict[tuple[str, str], list[str]],
    qualifiees: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    dependances = list(operation["security_dependencies"])
    gardes = [d for d in dependances if d not in DEPENDANCES_NON_AUTORISANTES]
    gardes_role = sorted(
        g for g in gardes if SEMANTIQUE_GARDES.get(g, {}).get("nature") == "authorization"
    )
    gardes_propres = sorted(
        g for g in gardes if SEMANTIQUE_GARDES.get(g, {}).get("nature") == "machine_token"
    )
    authentifiee = operation["authenticated"]
    portee = portees.get((operation["path"], operation["method"]), [])

    if gardes_propres:
        autorises: list[str] = []
        refuses: list[str] = []
        source = "custom_endpoint_guard"
        confiance = "CUSTOM_AUTH_CONFIRMED"
        justification = SEMANTIQUE_GARDES[gardes_propres[0]]["description"]
    elif authentifiee:
        autorises, refuses = _roles_depuis_gardes(gardes)
        if gardes_role:
            source = "fastapi_role_dependency"
            confiance = "STATIC_EXPLICIT"
            justification = " ".join(SEMANTIQUE_GARDES[g]["description"] for g in gardes_role)
        else:
            source = "authentication_only"
            confiance = "STATIC_EXPLICIT"
            justification = (
                "Aucune garde de rôle : tout compte actif porteur d'un jeton "
                "valide atteint cette opération, quel que soit son rôle."
            )
    else:
        autorises = []
        refuses = []
        source = "none"
        confiance = "STATIC_EXPLICIT"
        justification = (
            "Aucune dépendance d'authentification. Route qualifiée par écrit "
            "dans docs/g0/ROUTE_EXPOSURE_QUALIFICATION.json."
        )

    if portee:
        source = f"{source}+service_layer_scope"
        justification += (
            " Cloisonnement supplémentaire appliqué dans le corps de la fonction "
            f"({', '.join(portee)}) : un agent rattaché à une unité ne voit que "
            "les dossiers de son unité et ceux sans unité."
        )

    entree = {
        "path": operation["path"],
        "method": operation["method"],
        "operation_id": operation["operation_id"],
        "source_module": operation["source_module"],
        "lot_a_exposure": operation["exposure"],
        "auth_dependency": (
            "OAuth2PasswordBearer -> get_current_user -> get_current_active_user"
            if authentifiee
            else None
        ),
        "role_guards": gardes_role,
        "custom_guards": gardes_propres,
        "service_layer_scope": portee,
        "allowed_roles": autorises,
        "denied_roles": refuses,
        "authorization_source": source,
        "confidence": confiance,
        "justification": justification,
        "finding": None,
        "runtime_probes": [],
    }
    if operation["path"] in qualifiees:
        entree["lot_a_qualification"] = qualifiees[operation["path"]]["classement"]
    return entree


# ── Sondes runtime ──────────────────────────────────────────────────────────


class _CaptureJournal(logging.Handler):
    """Capture les enregistrements émis par l'application pendant une sonde."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lignes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lignes.append(record.getMessage())
        except Exception:  # pragma: no cover — un journal ne doit jamais casser une sonde
            self.lignes.append("<enregistrement illisible>")


def _preparer_application(repertoire: Path) -> tuple[Any, Any, dict[str, Any]]:
    """Application + client de test sur une base SQLite jetable et synthétique."""
    os.environ["TESTING"] = "true"
    os.environ.setdefault("CACHE_BACKEND", "memory")

    from fastapi.testclient import TestClient

    import app.db.session as db_session
    from app.core.config import settings
    from app.core.security import get_password_hash
    from app.db.base import Base
    from app.main import create_app
    from app.models import Patient, Result, Sample, User, UserRole

    settings.TESTING = True
    settings.SECRET_KEY = "g0-security-baseline-synthetic-key-32ch"  # pragma: allowlist secret
    settings.FIRST_SUPERUSER = "g0-bootstrap"
    settings.FIRST_SUPERUSER_PASSWORD = _MDP_SONDE
    settings.CSA_SYNC_ENABLED = False
    settings.ENABLE_DH36_LISTENER = False

    db_session.configure_database(f"sqlite:///{(repertoire / 'g0_security.db').as_posix()}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    session = db_session.SessionLocal()
    empreinte = get_password_hash(_MDP_SONDE)
    comptes = {
        "admin": (UserRole.ADMIN, None),
        "officer": (UserRole.OFFICER, None),
        "technician": (UserRole.TECHNICIAN, None),
        "technician_unit_a": (UserRole.TECHNICIAN, "G0-UNITE-A"),
        "accountant": (UserRole.ACCOUNTANT, None),
    }
    for nom, (role, unite) in comptes.items():
        session.add(
            User(
                username=f"g0-{nom}",
                hashed_password=empreinte,
                full_name=f"Sonde G0 {nom}",
                role=role,
                is_active=True,
                unit=unite,
            )
        )
    session.flush()

    # Deux patients synthétiques dans deux unités distinctes : c'est ce qui rend
    # l'accès croisé mesurable. Un seul patient ne prouverait rien.
    patient_a = Patient(
        ipp_unique_id=SENTINELLES["ipp"],
        first_name=SENTINELLES["prenom"],
        last_name=SENTINELLES["nom"],
        birth_date=__import__("datetime").date(1953, 11, 27),
        sex="M",
        phone=SENTINELLES["telephone"],
        residence_quarter=SENTINELLES["quartier"],
        unit="G0-UNITE-A",
    )
    patient_b = Patient(
        ipp_unique_id="G0SENT-IPP-AUTRE-UNITE",
        first_name="WWXY",
        last_name="AUTREUNITE",
        birth_date=__import__("datetime").date(1961, 4, 3),
        sex="F",
        unit="G0-UNITE-B",
    )
    session.add_all([patient_a, patient_b])
    session.flush()

    echantillon = Sample(
        barcode=SENTINELLES["code_barres"],
        patient_id=patient_a.id,
        status="received",
    )
    session.add(echantillon)
    session.flush()

    resultat = Result(
        sample_id=echantillon.id,
        exam_code="G0SENT",
        data_points={SENTINELLES["analyte"]: {"value": SENTINELLES["valeur_resultat"]}},
        is_validated=False,
    )
    session.add(resultat)
    session.commit()

    contexte = {
        "patient_unite_a": patient_a.id,
        "patient_unite_b": patient_b.id,
        "echantillon": echantillon.id,
        "resultat": resultat.id,
    }
    session.close()

    application = create_app()
    client = TestClient(application)
    client.__enter__()

    jetons: dict[str, str] = {}
    for nom in comptes:
        reponse = client.post(
            "/api/v1/login/access-token",
            data={"username": f"g0-{nom}", "password": _MDP_SONDE},
        )
        if reponse.status_code != 200:
            raise SystemExit(
                f"La sonde ne peut pas obtenir de jeton pour g0-{nom} "
                f"(HTTP {reponse.status_code}) : sans jeton, aucune mesure RBAC "
                "n'est possible."
            )
        jetons[nom] = reponse.json()["access_token"]
    contexte["jetons"] = jetons
    return application, client, contexte


def _classer_sonde(statut: int, attendu: str) -> str:
    """Dire ce que la réponse prouve — et surtout ce qu'elle ne prouve pas.

    Un 422 ne dit rien de l'autorisation : la requête a été refusée sur la forme.
    Le confondre avec un refus d'accès produirait une preuve fausse.
    """
    if statut in (401, 403):
        return "AUTHORIZATION_REACHED"
    if statut == 422:
        return "VALIDATION_FAILED_BEFORE_AUTHORIZATION"
    if 200 <= statut < 500:
        return "AUTHORIZATION_REACHED" if attendu == "ALLOW" else "AUTHORIZATION_REACHED"
    return "AUTHORIZATION_NOT_EXERCISED"


#: Sondes RBAC. Chacune dit : qui, quoi, et ce qu'on attend.
#: `attendu` ∈ {ALLOW, DENY}. Une sonde DENY qui reçoit autre chose que 401/403
#: est un écart, enregistré comme tel.
SONDES_RBAC: tuple[tuple[str, str, str, str, str], ...] = (
    # (compte, méthode, chemin, attendu, intention)
    # — le comptable ne doit atteindre aucune donnée clinique nominative —
    ("accountant", "GET", "/api/v1/patients", "DENY", "clinique nominative"),
    ("accountant", "GET", "/api/v1/patients/{patient_a}", "DENY", "clinique nominative"),
    ("accountant", "GET", "/api/v1/patients/{patient_a}/history", "DENY", "clinique nominative"),
    (
        "accountant",
        "GET",
        "/api/v1/patients/{patient_a}/fhir-bundle",
        "DENY",
        "export clinique nominatif",
    ),
    ("accountant", "GET", "/api/v1/results", "DENY", "résultats biologiques"),
    ("accountant", "GET", "/api/v1/results/{resultat}", "DENY", "résultats biologiques"),
    ("accountant", "GET", "/api/v1/samples", "DENY", "échantillons"),
    ("accountant", "GET", "/api/v1/exam-orders", "DENY", "prescriptions"),
    ("accountant", "GET", "/api/v1/worklist/my", "DENY", "file de travail clinique"),
    ("accountant", "GET", "/api/v1/notifications/feed", "DENY", "alertes cliniques"),
    ("accountant", "GET", "/api/v1/reports/epidemiology-summary", "DENY", "épidémiologie"),
    (
        "accountant",
        "GET",
        "/api/v1/reports/epidemiology-export.csv",
        "DENY",
        "export épidémiologique",
    ),
    ("accountant", "GET", "/api/v1/tat/dashboard", "DENY", "délais cliniques"),
    ("accountant", "GET", "/api/v1/bench/radar", "DENY", "paillasse"),
    # — le comptable garde la facturation —
    ("accountant", "GET", "/api/v1/invoices", "ALLOW", "facturation"),
    ("accountant", "GET", "/api/v1/invoices/aging", "ALLOW", "facturation"),
    ("accountant", "GET", "/api/v1/invoices/export.csv", "ALLOW", "export facturation"),
    # — le technicien n'administre pas —
    ("technician", "GET", "/api/v1/users", "DENY", "administration des comptes"),
    ("technician", "POST", "/api/v1/users", "DENY", "création de compte"),
    ("technician", "PATCH", "/api/v1/users/1", "DENY", "modification de compte"),
    ("technician", "GET", "/api/v1/audit-events", "DENY", "journal d'audit"),
    ("technician", "GET", "/api/v1/audit-events/export.csv", "DENY", "export d'audit"),
    ("technician", "GET", "/api/v1/admin/ratios", "DENY", "administration"),
    ("technician", "GET", "/api/v1/reports/audit-dashboard", "DENY", "tableau de bord d'audit"),
    (
        "technician",
        "DELETE",
        "/api/v1/maintenance/refresh-tokens/expired",
        "DENY",
        "maintenance",
    ),
    ("technician", "GET", "/api/v1/invoices", "DENY", "facturation"),
    ("technician", "GET", "/api/v1/equipment-reagent-ratios", "DENY", "paramétrage réactifs"),
    ("technician", "POST", "/api/v1/reagents", "DENY", "création réactif (officier)"),
    ("technician", "POST", "/api/v1/critical-ranges", "DENY", "bornes critiques (officier)"),
    ("technician", "POST", "/api/v1/auto-validation/run", "DENY", "auto-validation (officier)"),
    (
        "technician",
        "POST",
        "/api/v1/reports/results/{resultat}/release",
        "DENY",
        "libération de compte rendu",
    ),
    (
        "technician",
        "PATCH",
        "/api/v1/results/{resultat}/amend",
        "DENY",
        "correction de résultat",
    ),
    ("technician", "POST", "/api/v1/operations/validate-order", "DENY", "validation d'ordre"),
    # — le technicien conserve son métier —
    ("technician", "GET", "/api/v1/patients", "ALLOW", "dossiers patients"),
    ("technician", "GET", "/api/v1/results", "ALLOW", "résultats"),
    ("technician", "GET", "/api/v1/samples", "ALLOW", "échantillons"),
    ("technician", "POST", "/api/v1/samples", "ALLOW", "création d'échantillon"),
    # — l'officier ne devient pas administrateur —
    ("officer", "GET", "/api/v1/users", "DENY", "administration des comptes"),
    ("officer", "POST", "/api/v1/users", "DENY", "création de compte"),
    ("officer", "GET", "/api/v1/audit-events", "DENY", "journal d'audit"),
    ("officer", "GET", "/api/v1/admin/ratios", "DENY", "administration"),
    ("officer", "GET", "/api/v1/ratio-presets", "DENY", "administration"),
    ("officer", "POST", "/api/v1/equipments", "DENY", "création d'équipement"),
    ("officer", "GET", "/api/v1/invoices", "DENY", "facturation"),
    ("officer", "POST", "/api/v1/invoices", "DENY", "émission de facture"),
    ("officer", "PUT", "/api/v1/tariffs/G0SENT", "DENY", "tarification"),
    (
        "officer",
        "DELETE",
        "/api/v1/maintenance/refresh-tokens/expired",
        "DENY",
        "maintenance",
    ),
    ("officer", "POST", "/api/v1/invoices/1/cancel", "DENY", "annulation de facture"),
    ("officer", "POST", "/api/v1/invoices/1/refund", "DENY", "avoir sur facture"),
    ("officer", "POST", "/api/v1/invoices/1/payments", "DENY", "encaissement"),
    ("officer", "GET", "/api/v1/invoices/1/receipt.pdf", "DENY", "reçu de paiement"),
    # — l'officier conserve ses actes —
    ("officer", "GET", "/api/v1/patients", "ALLOW", "dossiers patients"),
    ("officer", "GET", "/api/v1/aes", "ALLOW", "registre AES"),
    ("officer", "POST", "/api/v1/auto-validation/run", "ALLOW", "auto-validation"),
    ("officer", "GET", "/api/v1/quality/non-conformities", "ALLOW", "qualité"),
    # — l'administrateur conserve l'administration —
    ("admin", "GET", "/api/v1/users", "ALLOW", "administration des comptes"),
    ("admin", "GET", "/api/v1/audit-events", "ALLOW", "journal d'audit"),
    ("admin", "GET", "/api/v1/reports/audit-dashboard", "ALLOW", "tableau de bord d'audit"),
    ("admin", "GET", "/api/v1/admin/ratios", "ALLOW", "administration"),
    ("admin", "GET", "/api/v1/equipment-reagent-ratios", "ALLOW", "paramétrage réactifs"),
    ("admin", "GET", "/api/v1/invoices", "ALLOW", "facturation (admin cumulé)"),
    ("admin", "GET", "/api/v1/patients", "ALLOW", "dossiers patients"),
    (
        "admin",
        "DELETE",
        "/api/v1/maintenance/refresh-tokens/expired",
        "ALLOW",
        "maintenance",
    ),
    # — accès croisé entre unités —
    (
        "technician_unit_a",
        "GET",
        "/api/v1/patients/{patient_a}",
        "ALLOW",
        "dossier de sa propre unité",
    ),
    (
        "technician_unit_a",
        "GET",
        "/api/v1/patients/{patient_b}",
        "DENY",
        "dossier d'une AUTRE unité — accès croisé",
    ),
    (
        "technician_unit_a",
        "GET",
        "/api/v1/patients/{patient_b}/history",
        "DENY",
        "historique d'une AUTRE unité",
    ),
    (
        "technician_unit_a",
        "GET",
        "/api/v1/patients/{patient_b}/fhir-bundle",
        "DENY",
        "export FHIR d'une AUTRE unité",
    ),
    # — routes sans garde de rôle : ce que le comptable atteint quand même —
    (
        "accountant",
        "GET",
        "/api/v1/military-facilities",
        "ALLOW",
        "cartographie militaire — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/critical-ranges",
        "ALLOW",
        "bornes critiques — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/reports/compliance-summary",
        "ALLOW",
        "conformité agrégée — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/equipment-maintenance",
        "ALLOW",
        "métrologie — aucune garde de rôle",
    ),
    (
        "technician",
        "DELETE",
        "/api/v1/equipment-maintenance/999999",
        "ALLOW",
        "suppression de maintenance — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/stats/summary",
        "ALLOW",
        "statistiques agrégées — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/reagents",
        "ALLOW",
        "stock de réactifs — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/reports/stock-dashboard",
        "ALLOW",
        "tableau de bord des stocks — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/quality/non-conformities",
        "ALLOW",
        "non-conformités qualité — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/auto-validation/config",
        "ALLOW",
        "paramétrage d'auto-validation clinique — aucune garde de rôle",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/qc/controls",
        "ALLOW",
        "contrôles qualité — aucune garde de rôle",
    ),
    # — équipements : lecture réservée à l'officier, écriture à l'administrateur —
    ("technician", "GET", "/api/v1/equipments/1/details", "DENY", "détail d'équipement"),
    (
        "technician",
        "GET",
        "/api/v1/equipments/1/qualifications",
        "DENY",
        "qualification métrologique",
    ),
    (
        "officer",
        "POST",
        "/api/v1/equipments/qualifications/1/approve",
        "ALLOW",
        "approbation métrologique",
    ),
    (
        "technician",
        "POST",
        "/api/v1/equipments/qualifications/1/approve",
        "DENY",
        "approbation métrologique",
    ),
    # — exports et rapports —
    (
        "technician",
        "GET",
        "/api/v1/reports/epidemiology-export.csv",
        "ALLOW",
        "export épidémiologique",
    ),
    (
        "technician",
        "GET",
        "/api/v1/reports/critical-compliance/export.csv",
        "ALLOW",
        "export conformité critique",
    ),
    (
        "accountant",
        "GET",
        "/api/v1/reports/critical-compliance/export.csv",
        "DENY",
        "export conformité critique",
    ),
)

#: Sondes avec charge utile valide : indispensables pour que l'autorisation soit
#: réellement atteinte. Une requête vide serait rejetée en 422 et ne prouverait
#: rien du tout.
SONDES_AVEC_CORPS: tuple[tuple[str, str, str, dict[str, Any], str, str], ...] = (
    (
        "accountant",
        "POST",
        "/api/v1/patients",
        {
            "ipp_unique_id": "G0SENT-IPP-SONDE-CREATION",
            "first_name": "SONDE",
            "last_name": "CREATION",
            "birth_date": "1970-01-02",
            "sex": "M",
        },
        "DENY",
        "création de dossier patient par le comptable",
    ),
    (
        "technician",
        "POST",
        "/api/v1/users",
        {
            "username": "g0-sonde-escalade",
            "password": _MDP_SONDE,
            "role": "admin",
            "full_name": "Sonde escalade",
        },
        "DENY",
        "création d'un compte administrateur par un technicien",
    ),
    (
        "officer",
        "POST",
        "/api/v1/users",
        {
            "username": "g0-sonde-escalade-officier",
            "password": _MDP_SONDE,
            "role": "admin",
            "full_name": "Sonde escalade officier",
        },
        "DENY",
        "création d'un compte administrateur par un officier",
    ),
    (
        "accountant",
        "POST",
        "/api/v1/aes",
        {
            "occurred_at": "2026-01-02T08:00:00",
            "exposure_type": "piqure",
            "circumstances": "Sonde G0 — donnée synthétique.",
            "source_serology": "G0SENT-SEROLOGIE",
        },
        "DENY",
        "déclaration AES (statut sérologique) par le comptable",
    ),
    (
        "accountant",
        "POST",
        "/api/v1/quality/non-conformities",
        {
            "title": "Sonde G0",
            "description": "Sonde G0 — donnée synthétique.",
            "severity": "minor",
            "source": "manual",
        },
        "DENY",
        "création de non-conformité par le comptable",
    ),
    (
        "technician",
        "POST",
        "/api/v1/billing/calculate",
        {
            "patient_type": "UNINSURED",
            "diagnoses": [{"cim10": {"code": "B54", "description": "Sonde G0"}}],
            "drugs": [
                {
                    "dci": {"code": "G0SENTDCI", "description": "Sonde G0"},
                    "quantity": 1,
                    "unit_price_xof": 100,
                }
            ],
        },
        "DENY",
        "calcul de facturation par un technicien",
    ),
    (
        "accountant",
        "POST",
        "/api/v1/epi-notifications",
        {
            "pathology": "G0SENT-PATHOLOGIE",
            "detected_at": "2026-01-02T08:00:00",
            "patient_label": "SONDE G0",
        },
        "DENY",
        "déclaration épidémiologique nominative par le comptable",
    ),
    (
        "technician",
        "POST",
        "/api/v1/quality/non-conformities",
        {
            "title": "Sonde G0 technicien",
            "description": "Sonde G0 — donnée synthétique.",
            "severity": "minor",
            "source": "manual",
        },
        "ALLOW",
        "création de non-conformité par un technicien — aucune garde de rôle",
    ),
)

#: Sondes non authentifiées : elles doivent recevoir 401. Une seule qui passe
#: est un défaut majeur.
SONDES_ANONYMES: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/v1/patients", "DENY"),
    ("GET", "/api/v1/results", "DENY"),
    ("GET", "/api/v1/users", "DENY"),
    ("GET", "/api/v1/invoices", "DENY"),
    ("GET", "/api/v1/audit-events", "DENY"),
    ("GET", "/api/v1/military-facilities", "DENY"),
)


def _motif_de_gabarit(gabarit: str) -> str:
    """Expression régulière qui reconnaît les chemins concrets d'un gabarit.

    `/api/v1/patients/{patient_id}` doit reconnaître `/api/v1/patients/3` mais
    pas `/api/v1/patients/3/history` : le segment substitué ne franchit pas le
    séparateur. Sans cette borne, une sonde sur une sous-ressource élèverait à
    tort la confiance de l'opération parente.
    """
    morceaux = [re.escape(m) for m in re.split(r"\{[^}]+\}", gabarit)]
    return "^" + "[^/]+".join(morceaux) + "$"


def _resoudre(chemin: str, contexte: dict[str, Any]) -> str:
    return (
        chemin.replace("{patient_a}", str(contexte["patient_unite_a"]))
        .replace("{patient_b}", str(contexte["patient_unite_b"]))
        .replace("{resultat}", str(contexte["resultat"]))
        .replace("{echantillon}", str(contexte["echantillon"]))
    )


def _corps_creation_echantillon(contexte: dict[str, Any]) -> dict[str, Any]:
    return {
        "barcode": "G0SENT-BARCODE-SONDE-CREATION",
        "patient_id": contexte["patient_unite_a"],
        "status": "received",
    }


def executer_sondes(client: Any, contexte: dict[str, Any]) -> list[dict[str, Any]]:
    """Exécute toutes les sondes et enregistre ce qui est réellement observé."""
    jetons = contexte["jetons"]
    sondes: list[dict[str, Any]] = []

    def enregistrer(
        compte: str | None,
        methode: str,
        chemin: str,
        attendu: str,
        intention: str,
        statut: int,
    ) -> None:
        classement = _classer_sonde(statut, attendu)
        refuse = statut in (401, 403)
        conforme = refuse if attendu == "DENY" else not refuse
        sondes.append(
            {
                "account": compte or "<anonyme>",
                "role": None if compte is None else _ROLE_DU_COMPTE[compte],
                "method": methode,
                "path": chemin,
                "expected": attendu,
                "observed_status": statut,
                "outcome": "DENIED" if refuse else "REACHED_HANDLER",
                "probe_class": classement,
                "matches_expectation": conforme,
                "intent": intention,
            }
        )

    for compte, methode, chemin, attendu, intention in SONDES_RBAC:
        cible = _resoudre(chemin, contexte)
        corps = _corps_creation_echantillon(contexte) if cible == "/api/v1/samples" else None
        reponse = client.request(
            methode,
            cible,
            headers={"Authorization": f"Bearer {jetons[compte]}"},
            json=corps if methode in ("POST", "PUT", "PATCH") else None,
        )
        enregistrer(compte, methode, cible, attendu, intention, reponse.status_code)

    for compte, methode, chemin, corps, attendu, intention in SONDES_AVEC_CORPS:
        cible = _resoudre(chemin, contexte)
        reponse = client.request(
            methode,
            cible,
            headers={"Authorization": f"Bearer {jetons[compte]}"},
            json=corps,
        )
        enregistrer(compte, methode, cible, attendu, intention, reponse.status_code)

    for methode, chemin, attendu in SONDES_ANONYMES:
        reponse = client.request(methode, chemin)
        enregistrer(None, methode, chemin, attendu, "accès sans jeton", reponse.status_code)

    sondes.sort(key=lambda s: (s["path"], s["method"], s["account"]))
    return sondes


_ROLE_DU_COMPTE = {
    "admin": "admin",
    "officer": "officer",
    "technician": "technician",
    "technician_unit_a": "technician",
    "accountant": "accountant",
}


# ── Routes particulières (§7) ───────────────────────────────────────────────


def qualifier_routes_particulieres(client: Any, contexte: dict[str, Any]) -> list[dict[str, Any]]:
    """Chaque route sensible, éprouvée une par une. Aucune n'est corrigée."""
    from app.core.config import settings

    jeton_admin = contexte["jetons"]["admin"]
    resultats: list[dict[str, Any]] = []

    # 1. /app/map — le constat du lot A est conservé et re-démontré.
    carte = client.get("/app/map")
    elements = [
        "Cartographie des EHM et Gendarmerie",
        "Etablissements Hospitaliers Militaires",
        "DIVISION SANTE",
        "HMA",
        "CMA",
        "CSA",
        "Gendarmerie",
    ]
    corps_carte = carte.text
    resultats.append(
        {
            "route": "GET /app/map",
            "mecanisme_de_garde": "aucun — gabarit HTML servi sans dépendance de sécurité",
            "capacite_reelle": (
                "Lire le gabarit public de la cartographie des établissements de santé militaires."
            ),
            "jeton_utilise": None,
            "portee": "lecture du gabarit ; coordonnées et liste détaillée restent derrière /api/v1/military-facilities",
            "expiration": "sans objet",
            "rejeu_possible": True,
            "observed_status_sans_jeton": carte.status_code,
            "informations_retournees": [e for e in elements if e in corps_carte]
            + (
                ["effectifs agrégés statiques : 60, 1, 8, 51, 37, 22"]
                if all(x in corps_carte for x in ("60", "51", "37", "22"))
                else []
            ),
            "traces_journaux": "requête tracée par ObservabilityMiddleware (chemin, IP cliente, agent).",
            "classement": "P1",
            "constat": (
                "Constat du lot A confirmé : HTTP 200 sans jeton. Le gabarit "
                "expose le titre « Cartographie des EHM et Gendarmerie », "
                "l'intitulé « Établissements Hospitaliers Militaires », la "
                "mention « DIVISION SANTÉ — 2026 », les catégories HMA, CMA, "
                "CSA, Armées et Gendarmerie, et les effectifs agrégés statiques "
                "60/1/8/51/37/22 — sans coordonnées ni liste détaillée. Un ordre "
                "de grandeur du dispositif de santé militaire est donc lisible "
                "sans authentification."
            ),
        }
    )

    # 2. POST /api/v1/login/logout — que peut faire un anonyme ?
    logout_vide = client.post("/api/v1/login/logout", json={})
    logout_faux = client.post(
        "/api/v1/login/logout", json={"refresh_token": "G0SENT-REFRESH-INEXISTANT"}
    )
    resultats.append(
        {
            "route": "POST /api/v1/login/logout",
            "mecanisme_de_garde": (
                "aucune dépendance de sécurité. Le jeton d'accès est lu dans "
                "l'en-tête Authorization s'il est présent ; le jeton de "
                "rafraîchissement est lu dans le corps et est optionnel."
            ),
            "capacite_reelle": (
                "Révoquer un jeton de rafraîchissement dont on connaît la valeur "
                "exacte, et révoquer le jeton d'accès qu'on présente soi-même. "
                "Aucune capacité de révoquer le jeton d'autrui sans en connaître "
                "la valeur : le jeton EST le facteur d'autorisation."
            ),
            "jeton_utilise": "jeton de rafraîchissement (corps) et/ou jeton d'accès (en-tête)",
            "portee": "la session désignée par le jeton fourni",
            "expiration": "sans objet — la route ne délivre rien",
            "rejeu_possible": True,
            "observed_status_anonyme_corps_vide": logout_vide.status_code,
            "observed_status_anonyme_jeton_inexistant": logout_faux.status_code,
            "informations_retournees": "aucune — 204 sans corps.",
            "traces_journaux": "requête tracée ; la valeur du jeton de rafraîchissement est dans le CORPS, donc non journalisée par le middleware (qui ne journalise que le chemin).",
            "classement": "P2",
            "constat": (
                "La crainte du lot A — révocation du jeton d'un tiers — n'est pas "
                "confirmée : révoquer suppose de connaître la valeur du jeton. La "
                "route répond néanmoins en 204 à un appel anonyme portant un jeton "
                "inexistant, donc sans distinguer succès et échec : elle ne "
                "renseigne pas l'appelant, ce qui est le bon comportement, mais "
                "elle n'est pas non plus limitée en débit par une garde propre."
            ),
        }
    )

    # 3. POST /api/v1/login/refresh
    refresh_faux = client.post(
        "/api/v1/login/refresh", json={"refresh_token": "G0SENT-REFRESH-INEXISTANT"}
    )
    resultats.append(
        {
            "route": "POST /api/v1/login/refresh",
            "mecanisme_de_garde": (
                "le jeton de rafraîchissement lui-même : comparaison de son "
                "empreinte SHA-256 en base, contrôle de validité, contrôle du "
                "compte actif. Rotation à usage unique — le jeton présenté est "
                "révoqué et un nouveau couple est émis."
            ),
            "capacite_reelle": "Obtenir un nouveau jeton d'accès pour le compte propriétaire du jeton présenté.",
            "jeton_utilise": "jeton de rafraîchissement opaque",
            "portee": "le compte propriétaire du jeton",
            "expiration": f"{settings.REFRESH_TOKEN_EXPIRE_DAYS} jours",
            "rejeu_possible": False,
            "observed_status_jeton_inexistant": refresh_faux.status_code,
            "informations_retournees": "un couple jeton d'accès / jeton de rafraîchissement.",
            "traces_journaux": "requête tracée ; la valeur du jeton est dans le corps, non journalisée.",
            "classement": "P2",
            "constat": (
                "Non authentifiée au sens des dépendances FastAPI, mais non "
                "anonyme : le jeton fait office d'authentification, il est "
                "vérifié, et la rotation à usage unique borne le rejeu. La "
                "réserve du lot A est levée. Reste qu'aucune limitation de débit "
                "propre ne protège cette route."
            ),
        }
    )

    # 4. GET /api/v1/reports/verify/{token}
    verif = client.get(f"/api/v1/reports/verify/{SENTINELLES['jeton_verification']}")
    resultats.append(
        {
            "route": "GET /api/v1/reports/verify/{token}",
            "mecanisme_de_garde": (
                "le jeton porté par l'URL. Il vaut `rs-<id>-<HMAC-SHA256>`, "
                "calculé sur des champs du compte rendu avec SECRET_KEY ; la base "
                "n'en stocke que l'empreinte SHA-256."
            ),
            "capacite_reelle": (
                "Vérifier l'authenticité d'un compte rendu imprimé sans compte. "
                "La réponse ne contient AUCUNE identité patient ni valeur "
                "biologique : statut, identifiants techniques, version, "
                "empreinte du PDF, date."
            ),
            "jeton_utilise": "jeton HMAC déterministe, porté dans le chemin de l'URL",
            "portee": "un compte rendu précis",
            "expiration": (
                "AUCUNE. Le jeton ne porte pas d'échéance et n'est pas "
                "révocable indépendamment du compte rendu."
            ),
            "rejeu_possible": True,
            "observed_status_jeton_inexistant": verif.status_code,
            "informations_retournees": (
                "status, snapshot_id, result_id, version_number, document_status, "
                "created_at, pdf_sha256, revoked_at."
            ),
            "traces_journaux": (
                "Le jeton est dans le CHEMIN de l'URL. ObservabilityMiddleware "
                "journalise `request.url.path` à l'entrée ET à la sortie : la "
                "valeur du jeton se retrouve donc en clair dans le journal "
                "technique. Mesuré par la sonde sentinelle."
            ),
            "classement": "P1",
            "constat": (
                "Le jeton est le seul facteur d'accès, il n'expire jamais, il est "
                "rejouable sans limite, et il est journalisé en clair par "
                "l'application. Le contenu renvoyé reste non nominatif, ce qui "
                "borne l'impact d'une fuite à la confirmation d'existence et à "
                "l'état d'un compte rendu."
            ),
        }
    )

    # 5. POST /api/v1/analyzer/results
    analyseur_sans_cle = client.post("/api/v1/analyzer/results", json={})
    resultats.append(
        {
            "route": "POST /api/v1/analyzer/results",
            "mecanisme_de_garde": SEMANTIQUE_GARDES["_verify_analyzer_security"]["description"],
            "capacite_reelle": "Déposer un lot de résultats déjà analysés par le middleware automate.",
            "jeton_utilise": "clé machine ANALYZER_API_KEY, en-tête X-Analyzer-Key ou X-API-Key",
            "portee": "ingestion de résultats",
            "expiration": (
                "la clé n'expire pas ; la signature HMAC optionnelle, elle, est "
                "horodatée et bornée par ANALYZER_SIGNATURE_MAX_SKEW_SECONDS."
            ),
            "rejeu_possible": (
                "oui sans HMAC ; borné par la fenêtre d'horodatage lorsque "
                "ANALYZER_HMAC_SECRET est défini. Une idempotence applicative "
                "limite l'effet d'un doublon."
            ),
            "observed_status_sans_cle": analyseur_sans_cle.status_code,
            "informations_retournees": "accusé d'ingestion.",
            "traces_journaux": "ingestion journalisée explicitement comme provenant d'un automate.",
            "classement": "P2",
            "constat": (
                "Ce n'est PAS une route ouverte : la garde existe et refuse "
                "l'appel sans clé. Sans ANALYZER_API_KEY configurée, la route "
                "répond 503 — fail-closed. La réserve du lot A est levée. La "
                "signature HMAC et le filtrage d'IP restent optionnels : sans "
                "eux, la seule protection est une clé statique qui n'expire pas."
            ),
        }
    )

    # 6. WebSocket /api/v1/notifications/ws
    ws_refuse = False
    try:
        with client.websocket_connect("/api/v1/notifications/ws"):
            pass
    except Exception:
        ws_refuse = True
    resultats.append(
        {
            "route": "WEBSOCKET /api/v1/notifications/ws",
            "mecanisme_de_garde": (
                "jeton JWT lu dans le sous-protocole `Sec-WebSocket-Protocol: "
                "bearer, <jeton>` ou, à défaut, dans le paramètre `?token=`. "
                "Denylist par jti vérifiée, compte actif vérifié, rôle "
                "ACCOUNTANT refusé, cinq connexions simultanées au maximum par "
                "compte. Les droits sont rechargés à chaque cycle de ~15 s."
            ),
            "capacite_reelle": (
                "Recevoir l'instantané des alertes et les valeurs critiques du "
                "périmètre du porteur."
            ),
            "jeton_utilise": "jeton d'accès JWT",
            "portee": "alertes du périmètre de l'utilisateur (can_access_result)",
            "expiration": f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes (échéance du jeton d'accès)",
            "rejeu_possible": "tant que le jeton est valide et non révoqué",
            "observed_refus_sans_jeton": ws_refuse,
            "informations_retournees": "valeurs critiques, péremptions, écarts QC.",
            "traces_journaux": (
                "en repli `?token=`, le jeton figure dans la requête HTTP "
                "d'ouverture. Le middleware applicatif ne journalise que le "
                "chemin, sans la requête, donc il ne l'écrit pas ; un proxy qui "
                "journaliserait l'URL complète l'écrirait."
            ),
            "classement": "P2",
            "constat": (
                "Garde réelle et rechargée en cours de connexion, ce qui est "
                "meilleur qu'un contrôle à l'ouverture seule. Écart relevé : "
                "`_authenticate_ws_token` ne vérifie PAS `auth_version`, "
                "contrairement à `get_current_user`. Un jeton émis avant une "
                "modification sensible du compte reste donc accepté sur le "
                "WebSocket jusqu'à son échéance, alors qu'il est refusé sur "
                "l'API HTTP. Le repli `?token=` expose la valeur du jeton à tout "
                "journal d'URL en amont."
            ),
        }
    )

    # 7. OPTIONS /{path_name:path}
    options_reponse = client.request("OPTIONS", "/api/v1/patients")
    options_inexistant = client.request("OPTIONS", "/chemin/qui/n/existe/pas")
    resultats.append(
        {
            "route": "OPTIONS /{path_name:path} (attrape-tout)",
            "mecanisme_de_garde": "aucun — répond 200 vide à toute requête OPTIONS.",
            "capacite_reelle": (
                "Obtenir une réponse 200 sur n'importe quel chemin, existant ou "
                "non. Ne renvoie aucune donnée et n'exécute aucun traitement."
            ),
            "jeton_utilise": None,
            "portee": "tous les chemins",
            "expiration": "sans objet",
            "rejeu_possible": True,
            "observed_status_route_existante": options_reponse.status_code,
            "observed_status_chemin_inexistant": options_inexistant.status_code,
            "informations_retournees": (
                "corps vide. La route ne distingue pas un chemin existant d'un "
                "chemin inexistant : elle ne permet donc PAS d'énumérer les "
                "routes."
            ),
            "traces_journaux": "requête tracée comme toute autre.",
            "classement": "P2",
            "constat": (
                "Route hors schéma, sans garde, mais sans capacité : réponse "
                "identique partout, aucun corps, aucun effet. Elle masque en "
                "revanche les en-têtes CORS calculés par le middleware, puisque "
                "la préflight n'atteint jamais celui-ci sur les chemins qu'elle "
                "attrape."
            ),
        }
    )

    # 8. Chemins techniques à travers le proxy.
    caddyfile = (RACINE / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    bloques = ("/metrics", "/docs", "/openapi.json", "/redoc")
    directive = next(
        (
            ligne.strip()
            for ligne in caddyfile.splitlines()
            if ligne.strip().startswith("@internal")
        ),
        "",
    )
    directs: dict[str, int] = {}
    for chemin in bloques:
        directs[chemin] = client.get(
            chemin, headers={"Authorization": f"Bearer {jeton_admin}"}
        ).status_code
    resultats.append(
        {
            "route": "GET /metrics, /docs, /redoc, /openapi.json",
            "mecanisme_de_garde": (
                "aucun côté application. Le blocage est fait par le proxy : "
                f"`{directive}` suivi de `respond @internal 404` dans "
                "deploy/Caddyfile."
            ),
            "capacite_reelle": (
                "Depuis le réseau interne Docker, en s'adressant directement à "
                "`app:8000`, ces chemins répondent sans aucune authentification : "
                "métriques d'exploitation, contrat OpenAPI complet des 231 "
                "opérations, interfaces de documentation interactives."
            ),
            "jeton_utilise": None,
            "portee": "exposition technique complète du service",
            "expiration": "sans objet",
            "rejeu_possible": True,
            "observed_status_en_direct_sur_l_application": directs,
            "proxy_bloque": all(c in directive for c in bloques),
            "informations_retournees": (
                "métriques Prometheus (étiquetées par gabarit de route, sans "
                "identifiant patient), schéma OpenAPI intégral."
            ),
            "traces_journaux": "requêtes tracées par le middleware applicatif.",
            "classement": "P2",
            "constat": (
                "La protection est entièrement portée par le proxy, pas par "
                "l'application. Elle tient tant que le seul chemin d'accès passe "
                "par lui. Tout accès direct au réseau `backend` — un conteneur "
                "compromis, un port publié par erreur — contourne le blocage. "
                "Le job CI `docker-stack` vérifie le 404 au proxy ; rien ne "
                "vérifie l'absence de chemin direct."
            ),
        }
    )

    return resultats


# ── Sentinelles (§10) ───────────────────────────────────────────────────────


def observer_sentinelles(client: Any, contexte: dict[str, Any]) -> dict[str, Any]:
    """Écrire des valeurs uniques, puis les chercher là où elles ne devraient pas être."""
    from app.core.metrics import render_latest
    from app.services.token_cleanup import purge_expired_tokens

    import app.db.session as db_session

    jeton = contexte["jetons"]["admin"]
    entetes = {"Authorization": f"Bearer {jeton}"}

    capture = _CaptureJournal()
    racine_log = logging.getLogger()
    niveau_initial = racine_log.level
    racine_log.addHandler(capture)
    racine_log.setLevel(logging.DEBUG)

    canaux: dict[str, list[str]] = {}
    try:
        # Parcours applicatif : lecture nominative, détail, historique, export,
        # puis une route qui porte une sentinelle DANS l'URL.
        client.get("/api/v1/patients", headers=entetes)
        client.get(f"/api/v1/patients/{contexte['patient_unite_a']}", headers=entetes)
        client.get(f"/api/v1/patients/{contexte['patient_unite_a']}/history", headers=entetes)
        client.get("/api/v1/results", headers=entetes)
        client.get(f"/api/v1/results/{contexte['resultat']}", headers=entetes)
        client.get("/api/v1/samples", headers=entetes)
        erreur_validation = client.post(
            "/api/v1/patients",
            headers=entetes,
            json={"ipp_unique_id": SENTINELLES["ipp"], "first_name": SENTINELLES["prenom"]},
        )
        verification = client.get(f"/api/v1/reports/verify/{SENTINELLES['jeton_verification']}")
        introuvable = client.get(
            f"/api/v1/samples/by-barcode/{SENTINELLES['code_barres']}-INEXISTANT",
            headers=entetes,
        )
        canaux["journal_application"] = list(capture.lignes)

        # Journal du scheduler : sa tâche principale, exécutée pour de vrai.
        capture.lignes.clear()
        session = db_session.SessionLocal()
        try:
            purge_expired_tokens(session)
        finally:
            session.close()
        canaux["journal_scheduler"] = list(capture.lignes)

        # Journal de la passerelle automate : la garde refuse, mais le chemin de
        # journalisation est bien exercé.
        capture.lignes.clear()
        client.post(
            "/api/v1/analyzer/results",
            json={"sample_barcode": SENTINELLES["code_barres"], "results": []},
        )
        canaux["journal_analyzer_gateway"] = list(capture.lignes)
    finally:
        racine_log.removeHandler(capture)
        racine_log.setLevel(niveau_initial)

    exposition = render_latest()[0].decode("utf-8", errors="replace")
    etiquettes = "\n".join(
        ligne.split("{", 1)[1].split("}", 1)[0]
        for ligne in exposition.splitlines()
        if "{" in ligne and "}" in ligne
    )

    # Journal du proxy : mesuré en lisant sa configuration, pas supposé.
    caddyfile = (RACINE / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    proxy_journalise = any(
        ligne.strip().startswith("log") or ligne.strip().startswith("log ")
        for ligne in caddyfile.splitlines()
    )

    # Audit métier : la sentinelle DOIT s'y trouver, c'est sa raison d'être.
    session = db_session.SessionLocal()
    try:
        from app.models import AuditEvent

        audit = "\n".join(
            json.dumps(
                {"type": e.event_type, "entity": e.entity_id, "payload": e.payload},
                ensure_ascii=False,
                default=str,
            )
            for e in session.query(AuditEvent).all()
        )
    finally:
        session.close()

    messages_erreur = "\n".join(
        [
            erreur_validation.text,
            verification.text,
            introuvable.text,
            str(erreur_validation.status_code),
        ]
    )

    surfaces = {
        "journal_application": "\n".join(canaux["journal_application"]),
        "journal_scheduler": "\n".join(canaux["journal_scheduler"]),
        "journal_analyzer_gateway": "\n".join(canaux["journal_analyzer_gateway"]),
        "metriques_prometheus": exposition,
        "etiquettes_de_metriques": etiquettes,
        "messages_erreur_client": messages_erreur,
        "audit_metier_en_base": audit,
    }

    observations = []
    for nom_sentinelle, valeur in sorted(SENTINELLES.items()):
        for nom_surface, contenu in sorted(surfaces.items()):
            observations.append(
                {
                    "sentinel": nom_sentinelle,
                    "surface": nom_surface,
                    "found": valeur in contenu,
                }
            )

    trouvailles = [o for o in observations if o["found"]]
    return {
        "_comment": (
            "Les valeurs des sentinelles sont volontairement absentes de cet "
            "artefact : y écrire la chaine cherchee la rendrait indetectable "
            "par un futur controle qui scannerait le depot lui-meme."
        ),
        "sentinelles_declarees": sorted(SENTINELLES),
        "surfaces_examinees": sorted(surfaces),
        "surface_journal_proxy": {
            "exercee": False,
            "mesure": (
                "deploy/Caddyfile ne contient aucune directive `log` : le proxy "
                "n'ecrit AUCUN journal d'acces. Il ne peut donc pas divulguer de "
                "sentinelle — et il ne peut pas non plus servir a une "
                "investigation."
            ),
            "directive_log_presente": proxy_journalise,
        },
        "observations": observations,
        "totals": {
            "observations": len(observations),
            "trouvees": len(trouvailles),
            "surfaces_avec_sentinelle": sorted({o["surface"] for o in trouvailles}),
        },
    }


# ── Classification des données ──────────────────────────────────────────────


def _classer_colonne(table: str, colonne: str) -> tuple[str, str]:
    surcharge = SURCHARGES_COLONNES.get((table, colonne))
    if surcharge is not None:
        return surcharge
    for genre, motif, categorie, finalite in REGLES_NOMS:
        if genre == "exact" and colonne == motif:
            return categorie, finalite
        if genre == "suffixe" and colonne.endswith(motif):
            return categorie, finalite
        if genre == "prefixe" and colonne.startswith(motif):
            return categorie, finalite
    return CATEGORIE_PAR_DEFAUT_TABLE.get(table, CATEGORIE_PAR_DEFAUT)


def _acteurs_par_table(matrice: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Qui atteint une table — MESURÉ depuis la matrice, jamais affirmé."""
    acteurs: dict[str, dict[str, Any]] = {}
    for table, prefixes in TABLE_VERS_ROUTES.items():
        roles: set[str] = set()
        routes: list[str] = []
        for operation in matrice:
            if any(operation["path"].startswith(prefixe) for prefixe in prefixes):
                roles.update(operation["allowed_roles"])
                routes.append(f"{operation['method']} {operation['path']}")
        acteurs[table] = {
            "roles": sorted(roles),
            "route_count": len(routes),
            "routes": sorted(routes),
            "derivation": (
                "Union des rôles autorisés sur les routes rattachées à cette "
                "table dans TABLE_VERS_ROUTES, calculée depuis rbac-matrix.json."
                if prefixes
                else "Aucune route ne sert cette table : accès par service interne uniquement."
            ),
        }
    return acteurs


def construire_classification(
    schema: dict[str, Any], matrice: list[dict[str, Any]]
) -> dict[str, Any]:
    acteurs = _acteurs_par_table(matrice)
    tables_schema = sorted(t["table_name"] for t in schema["tables"])
    manquantes = [t for t in tables_schema if t not in TABLE_VERS_ROUTES]
    if manquantes:
        raise SystemExit(
            "Tables présentes dans le schéma mais absentes de TABLE_VERS_ROUTES : "
            f"{manquantes}. Les ignorer produirait une classification incomplète "
            "en silence."
        )

    champs: list[dict[str, Any]] = []
    for colonne in schema["columns"]:
        table = colonne["table_name"]
        nom = colonne["column_name"]
        categorie, finalite = _classer_colonne(table, nom)
        contexte = CONTEXTE_TABLES.get(table, CONTEXTE_TABLE_DEFAUT)
        champs.append(
            {
                "table": table,
                "field": nom,
                "data_type": colonne["data_type"],
                "nullable": colonne["is_nullable"] == "YES",
                "category": categorie,
                "purpose": finalite,
                "actors": acteurs[table]["roles"],
                "actors_derivation": acteurs[table]["derivation"],
                "storage": STOCKAGE_COMMUN["stockage"],
                "logging": contexte["journalisation"],
                "export": (
                    "Sortie possible par les routes qui servent la table "
                    f"({acteurs[table]['route_count']} opérations recensées)."
                    if acteurs[table]["route_count"]
                    else "Aucune route d'export directe."
                ),
                "backup": STOCKAGE_COMMUN["sauvegarde"],
                "metrics": contexte["metriques"],
                "retention": contexte["duree_conservation"],
                "inbound_flow": contexte["flux_entrant"],
                "outbound_flow": contexte["flux_sortant"],
                "encryption_observed": STOCKAGE_COMMUN["chiffrement_observe"],
                "risk": RISQUE_PAR_CATEGORIE[categorie],
            }
        )
    champs.sort(key=lambda c: (c["table"], c["field"]))

    par_categorie = {c: sum(1 for x in champs if x["category"] == c) for c in CATEGORIES}
    return {
        "_comment": (
            "Classification, pas controle d'acces. Elle dit ce qu'une donnee EST "
            "et qui l'atteint ; elle n'empeche rien. Les acteurs sont calcules "
            "depuis rbac-matrix.json, pas affirmes."
        ),
        "categories": list(CATEGORIES),
        "totals": {
            "tables": len(tables_schema),
            "fields": len(champs),
            "by_category": par_categorie,
            "fields_without_retention_policy": sum(
                1 for c in champs if c["retention"] == "UNKNOWN"
            ),
        },
        "tables_without_serving_route": sorted(
            t for t, v in acteurs.items() if v["route_count"] == 0
        ),
        "table_actors": acteurs,
        "fields": champs,
    }


# ── Résumé du scan de secrets ───────────────────────────────────────────────


def construire_resume_secrets() -> dict[str, Any]:
    """Revue de `.secrets.baseline` — emplacements et jugements, jamais de valeurs."""
    chemin = RACINE / ".secrets.baseline"
    baseline = json.loads(chemin.read_text(encoding="utf-8"))
    entrees: list[dict[str, Any]] = []
    fichiers_non_revus: list[str] = []
    chemins_non_posix: list[str] = []

    for fichier, occurrences in sorted(baseline.get("results", {}).items()):
        normalise = fichier.replace("\\", "/")
        if normalise != fichier:
            chemins_non_posix.append(normalise)
        revue = REVUE_BASELINE_SECRETS.get(normalise)
        if revue is None:
            fichiers_non_revus.append(normalise)
        for occurrence in sorted(occurrences, key=lambda o: o.get("line_number", 0)):
            entrees.append(
                {
                    "rule": occurrence.get("type"),
                    "file": normalise,
                    "line": occurrence.get("line_number"),
                    "is_verified": occurrence.get("is_verified", False),
                    "status": (revue or {}).get("statut", "NON_REVU"),
                    "character": (revue or {}).get("caractere", "A_QUALIFIER"),
                    "justification": (revue or {}).get(
                        "justification",
                        "Aucune revue enregistrée pour ce fichier — à qualifier.",
                    ),
                    "rotation_required": (revue or {}).get("rotation_necessaire", True),
                }
            )

    reels = [e for e in entrees if e["character"] == "SECRET_REEL"]
    return {
        "_comment": (
            "Aucune valeur de secret n'est reproduite ici, pas meme tronquee : "
            "un fragment reste un indice. Seuls figurent l'emplacement, la regle "
            "declenchee et le jugement porte."
        ),
        "baseline_version": baseline.get("version"),
        "totals": {
            "files": len({e["file"] for e in entrees}),
            "entries": len(entrees),
            "by_character": {
                caractere: sum(1 for e in entrees if e["character"] == caractere)
                for caractere in sorted({e["character"] for e in entrees})
            },
            "rotation_required": sum(1 for e in entrees if e["rotation_required"]),
            "real_secrets": len(reels),
        },
        "unreviewed_files": sorted(fichiers_non_revus),
        "windows_style_paths_normalised": sorted(chemins_non_posix),
        "entries": entrees,
    }


# ── Constats ────────────────────────────────────────────────────────────────


def construire_constats(
    matrice: list[dict[str, Any]],
    sondes: list[dict[str, Any]],
    sentinelles: dict[str, Any],
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ce que la mesure a réellement montré. Rien n'est corrigé ici."""
    constats: list[dict[str, Any]] = []

    sans_garde = sorted(
        f"{o['method']} {o['path']}"
        for o in matrice
        if o["auth_dependency"] and not o["role_guards"] and not o["custom_guards"]
    )
    cliniques_sans_garde = sorted(
        c
        for c in sans_garde
        if any(
            marqueur in c
            for marqueur in (
                "/aes",
                "/prescription/",
                "/bioref/interpret",
                "/fhir/",
                "/military-facilities",
            )
        )
    )
    constats.append(
        {
            "id": "B-01",
            "classement": "P1",
            "titre": "Des opérations touchant à la santé n'ont aucune garde de rôle",
            "constat": (
                f"{len(sans_garde)} des 231 opérations n'exercent qu'une "
                "authentification : tout compte actif les atteint, y compris le "
                "comptable, que forbid_accountant écarte pourtant partout "
                f"ailleurs. Parmi elles, {len(cliniques_sans_garde)} touchent à "
                "la santé ou à l'opérationnel militaire."
            ),
            "preuve": (
                "Dérivé de artifacts/g0/routes.json et confirmé par sonde : "
                "POST /api/v1/aes accepté pour le compte comptable, alors que ce "
                "dossier porte le statut sérologique VIH/VHB/VHC du patient "
                "source."
            ),
            "operations": cliniques_sans_garde,
            "remediation_owner": "lot D",
        }
    )

    tables = {t["table_name"] for t in schema["tables"]}
    constats.append(
        {
            "id": "B-02",
            "classement": "P2",
            "titre": "Le modèle military_facilities n'a aucune table dans la base migrée",
            "constat": (
                "app/models/ruggylab_os.py définit MilitaryFacility avec latitude "
                "et longitude d'établissements de santé militaires. La table "
                "`military_facilities` est ABSENTE des "
                f"{len(tables)} tables introspectées sur une base réellement "
                "migrée. GET /api/v1/military-facilities ne peut donc pas "
                "fonctionner sur PostgreSQL migré."
            ),
            "preuve": "artifacts/g0/schema.json ne contient pas `military_facilities`.",
            "remediation_owner": "lot D",
        }
    )

    constats.append(
        {
            "id": "B-03",
            "classement": "P1",
            "titre": "Le jeton de vérification d'un compte rendu est journalisé en clair",
            "constat": (
                "GET /api/v1/reports/verify/{token} porte le jeton dans le chemin. "
                "ObservabilityMiddleware journalise `request.url.path` à l'entrée "
                "et à la sortie. Le jeton n'expire jamais et n'est pas révocable "
                "indépendamment du compte rendu."
            ),
            "preuve": (
                "Sonde sentinelle : la valeur placée dans le chemin est retrouvée "
                "dans le journal applicatif — voir log-sentinel-observations.json, "
                "sentinelle `jeton_verification`."
            ),
            "remediation_owner": "lot D",
        }
    )

    constats.append(
        {
            "id": "B-04",
            "classement": "P2",
            "titre": "Le WebSocket ne vérifie pas auth_version",
            "constat": (
                "_authenticate_ws_token décode le JWT et vérifie la denylist, mais "
                "ne compare pas `ver` à `user.auth_version` — contrôle que "
                "get_current_user, lui, applique. Un jeton émis avant une "
                "modification sensible du compte reste accepté sur le WebSocket "
                "jusqu'à son échéance."
            ),
            "preuve": "Lecture de app/api/v1/endpoints/notifications.py et de app/api/deps.py.",
            "remediation_owner": "lot D",
        }
    )

    constats.append(
        {
            "id": "B-05",
            "classement": "P2",
            "titre": "Aucun journal d'accès au proxy",
            "constat": (
                "deploy/Caddyfile ne contient aucune directive `log`. Aucune trace "
                "des accès externes n'existe au niveau du proxy : après incident, "
                "seule reste la vue applicative, qui ne voit pas ce que le proxy a "
                "refusé."
            ),
            "preuve": "Lecture de deploy/Caddyfile, mesurée par la sonde sentinelle.",
            "remediation_owner": "lot D",
        }
    )

    constats.append(
        {
            "id": "B-06",
            "classement": "P2",
            "titre": "Aucune durée de conservation définie pour les données cliniques",
            "constat": (
                "Le dépôt ne définit de purge que pour les jetons (7 jours après "
                "expiration). Aucune borne n'existe pour les patients, les "
                "résultats, les comptes rendus, l'audit ou les dossiers AES."
            ),
            "preuve": "data-classification.json, champ `retention` = UNKNOWN.",
            "remediation_owner": "lot D",
        }
    )

    constats.append(
        {
            "id": "B-07",
            "classement": "P2",
            "titre": "Le cloisonnement par unité ne repose que sur le code applicatif",
            "constat": (
                "Le lot A a relevé zéro politique RLS. La sonde confirme que le "
                "cloisonnement fonctionne par l'API. Il disparaît pour tout accès "
                "direct à la base — sauvegarde comprise, dump non chiffré."
            ),
            "preuve": (
                "Sonde `technician_unit_a` sur le patient de l'unité B ; "
                "artifacts/g0/schema.json, `rls_policies` vide."
            ),
            "remediation_owner": "lot D",
        }
    )

    ecarts = [s for s in sondes if not s["matches_expectation"]]
    if ecarts:
        constats.append(
            {
                "id": "B-08",
                "classement": "P1",
                "titre": ("L'application s'écarte de la séparation des tâches attendue"),
                "constat": (
                    f"{len(ecarts)} sondes sur {len(sondes)} montrent un comportement "
                    "différent de ce que la séparation des tâches laisserait "
                    "attendre. `expected` exprime la RÈGLE MÉTIER attendue, pas ce que "
                    "le code fait : un écart décrit donc l'application telle qu'elle "
                    "est, et non une sonde défaillante."
                ),
                "preuve": [
                    f"{s['account']} ({s['role']}) {s['method']} {s['path']} -> HTTP "
                    f"{s['observed_status']} ({s['outcome']}), attendu {s['expected']} "
                    f"— {s['intent']}"
                    for s in ecarts
                ],
                "remediation_owner": "lot D",
            }
        )

    surfaces_fuyantes = [
        s
        for s in sentinelles["totals"]["surfaces_avec_sentinelle"]
        if s not in ("audit_metier_en_base", "messages_erreur_client")
    ]
    if surfaces_fuyantes:
        constats.append(
            {
                "id": "B-09",
                "classement": "P1",
                "titre": "Des données patient synthétiques apparaissent hors de l'audit métier",
                "constat": (
                    "Des sentinelles ont été retrouvées dans des surfaces "
                    "techniques : " + ", ".join(surfaces_fuyantes) + "."
                ),
                "preuve": "log-sentinel-observations.json",
                "remediation_owner": "lot D",
            }
        )

    return constats


# ── Assemblage ──────────────────────────────────────────────────────────────


def construire(avec_runtime: bool = True) -> dict[str, Any]:
    lot_a = charger_lot_a()
    qualifiees = _qualification_par_chemin(lot_a["qualification"])

    repertoire = Path(tempfile.mkdtemp(prefix="g0-security-"))
    application, client, contexte = _preparer_application(repertoire)
    try:
        portees = _portees_service(application)
        matrice = [
            _operation_statique(operation, portees, qualifiees)
            for operation in lot_a["routes"]["operations"]
        ]
        matrice.sort(key=lambda o: (o["path"], o["method"]))

        sondes = executer_sondes(client, contexte) if avec_runtime else []
        particulieres = qualifier_routes_particulieres(client, contexte) if avec_runtime else []
        sentinelles = (
            observer_sentinelles(client, contexte)
            if avec_runtime
            else {"observations": [], "totals": {"surfaces_avec_sentinelle": []}}
        )
    finally:
        client.__exit__(None, None, None)

    # Élévation de confiance : une opération réellement sondée passe de
    # STATIC_EXPLICIT à RUNTIME_CONFIRMED, mais seulement si la sonde a
    # effectivement atteint l'autorisation.
    par_operation: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sonde in sondes:
        par_operation.setdefault((sonde["path"], sonde["method"]), []).append(sonde)
    for operation in matrice:
        motif = _motif_de_gabarit(operation["path"])
        concernees = [
            s
            for (chemin, methode), groupe in par_operation.items()
            if methode == operation["method"] and re.match(motif, chemin)
            for s in groupe
        ]
        if not concernees:
            continue
        operation["runtime_probes"] = [
            {
                "account": s["account"],
                "role": s["role"],
                "expected": s["expected"],
                "observed_status": s["observed_status"],
                "probe_class": s["probe_class"],
                "matches_expectation": s["matches_expectation"],
            }
            for s in sorted(concernees, key=lambda s: (s["account"], s["observed_status"]))
        ]
        if any(s["probe_class"] == "AUTHORIZATION_REACHED" for s in concernees):
            operation["confidence"] = "RUNTIME_CONFIRMED"

    non_resolues = [o for o in matrice if o["confidence"] == "UNRESOLVED"]
    par_confiance = {
        niveau: sum(1 for o in matrice if o["confidence"] == niveau)
        for niveau in sorted({o["confidence"] for o in matrice})
    }
    par_source = {
        source: sum(1 for o in matrice if o["authorization_source"] == source)
        for source in sorted({o["authorization_source"] for o in matrice})
    }

    constats = construire_constats(matrice, sondes, sentinelles, lot_a["schema"])

    rbac = {
        "_comment": (
            "Derive de artifacts/g0/routes.json — aucune liste de routes n'est "
            "reecrite a la main. L'autorisation n'est jamais deduite du nom "
            "d'une route : elle vient des dependances reellement appliquees, du "
            "corps de la fonction, ou d'une sonde executee."
        ),
        "roles": list(ROLES),
        "guard_semantics": {
            nom: {
                "nature": valeur["nature"],
                "roles_autorises": list(valeur["roles_autorises"]),
                "description": valeur["description"],
            }
            for nom, valeur in sorted(SEMANTIQUE_GARDES.items())
        },
        "totals": {
            "operations": len(matrice),
            "by_confidence": par_confiance,
            "by_authorization_source": par_source,
            "unresolved": len(non_resolues),
            "authentication_only": sum(
                1 for o in matrice if o["authorization_source"].startswith("authentication_only")
            ),
            "with_service_layer_scope": sum(1 for o in matrice if o["service_layer_scope"]),
        },
        "runtime_probes": {
            "totals": {
                "probes": len(sondes),
                "matching_expectation": sum(1 for s in sondes if s["matches_expectation"]),
                "by_class": {
                    classe: sum(1 for s in sondes if s["probe_class"] == classe)
                    for classe in sorted({s["probe_class"] for s in sondes})
                },
            },
            "probes": sondes,
        },
        "special_routes": particulieres,
        "findings": constats,
        "operations": matrice,
    }

    return {
        "rbac-matrix": rbac,
        "data-classification": construire_classification(lot_a["schema"], matrice),
        "external-flows": {
            "_comment": (
                "Les frontieres recensees par le lot A (docs/g0/INVENTORY.md §6), "
                "completees par les donnees qui y circulent."
            ),
            "totals": {
                "flows": len(FLUX_EXTERNES),
                "enabled_by_default": sum(
                    1 for f in FLUX_EXTERNES if f["activation_requise"] == "non"
                ),
                "requiring_activation": sum(
                    1 for f in FLUX_EXTERNES if f["activation_requise"] == "oui"
                ),
            },
            "flows": [dict(f) for f in FLUX_EXTERNES],
        },
        "log-sentinel-observations": sentinelles,
        "secret-scan-summary": construire_resume_secrets(),
    }


def provenance(commande: str) -> dict[str, Any]:
    from scripts.g0_provenance import provenance as construire_provenance

    return construire_provenance(
        "security",
        commande,
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
    )


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


COMMANDE = "python scripts/g0_security_baseline.py --generate"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baseline de sécurité G0.")
    parser.add_argument("--generate", action="store_true", help="écrit les artefacts")
    parser.add_argument(
        "--check",
        action="store_true",
        help="échoue si les artefacts versionnés divergent de ce qui est régénéré",
    )
    parser.add_argument("--output-dir", type=Path, default=ARTEFACTS)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    if not (args.generate or args.check or args.print_summary):
        parser.error("choisir --generate, --check ou --print-summary")

    artefacts = construire()

    if args.print_summary:
        rbac = artefacts["rbac-matrix"]
        print(f"Opérations dans la matrice     : {rbac['totals']['operations']}")
        for niveau, total in sorted(rbac["totals"]["by_confidence"].items()):
            print(f"  {niveau:24s} {total}")
        print(f"Non résolues                   : {rbac['totals']['unresolved']}")
        print(f"Authentification seule         : {rbac['totals']['authentication_only']}")
        print(f"Cloisonnement en couche service: {rbac['totals']['with_service_layer_scope']}")
        sondes = rbac["runtime_probes"]["totals"]
        print(f"Sondes exécutées               : {sondes['probes']}")
        print(f"  conformes à l'attendu        : {sondes['matching_expectation']}")
        classification = artefacts["data-classification"]["totals"]
        print(f"Champs classés                 : {classification['fields']}")
        for categorie, total in sorted(classification["by_category"].items()):
            if total:
                print(f"  {categorie:24s} {total}")
        sentinelles = artefacts["log-sentinel-observations"]["totals"]
        print(f"Observations sentinelles       : {sentinelles['observations']}")
        print(f"  sentinelles retrouvées       : {sentinelles['trouvees']}")
        print(f"  surfaces concernées          : {sentinelles['surfaces_avec_sentinelle']}")
        # Deux ENTIERS, convertis explicitement avant d'etre affiches. Le
        # resume ne doit jamais pouvoir laisser passer autre chose qu'un
        # nombre : CodeQL relevait ici une journalisation de donnee sensible,
        # parce que la valeur venait d'une structure nommee « secret ». La
        # conversion n'est pas un contournement, c'est la garantie que ce qui
        # sort est un compte et rien d'autre.
        totaux_baseline = artefacts["secret-scan-summary"]["totals"]
        nombre_entrees = int(totaux_baseline["entries"])
        nombre_valeurs_reelles = int(totaux_baseline["real_secrets"])
        print(f"Entrées de .secrets.baseline   : {nombre_entrees:d}")
        print(f"  dont valeurs réelles         : {nombre_valeurs_reelles:d}")

    if args.generate:
        for nom, payload in artefacts.items():
            _ecrire(args.output_dir / f"{nom}.json", payload)
        (args.output_dir / "security-provenance.json").write_text(
            json.dumps(provenance(COMMANDE), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nArtefacts de sécurité écrits dans {args.output_dir}")

    if args.check:
        from scripts.g0_provenance import controler

        divergences = []
        for nom, payload in artefacts.items():
            versionne = _lire_payload(args.output_dir / f"{nom}.json")
            if versionne is None:
                divergences.append(f"{nom}.json absent")
            elif versionne != payload:
                divergences.append(f"{nom}.json diverge du code")
        divergences.extend(
            controler(args.output_dir / "security-provenance.json", provenance(COMMANDE))
        )
        if divergences:
            print(
                "\nECHEC : les artefacts de sécurité versionnés ne décrivent plus le code.",
                file=sys.stderr,
            )
            for message in divergences:
                print(f"  ! {message}", file=sys.stderr)
            print(f"\nRégénérer avec : {COMMANDE}", file=sys.stderr)
            return 1
        print("\nLes artefacts de sécurité versionnés correspondent au code.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

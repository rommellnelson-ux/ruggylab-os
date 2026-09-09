"""Baseline de performance G0 (preuve 8) — mesurer, pas juger.

Ce script exécute un scénario clinique **entièrement synthétique** contre une
stack RuggyLab OS réelle (application, PostgreSQL, Valkey, proxy, scheduler,
Prometheus) et enregistre ce qu'il observe. Il n'énonce aucun objectif de
latence et n'en accepte aucun : une latence élevée est un **résultat**, pas un
échec. Ce qui fait échouer ce script, c'est une mesure *invalide* — une mesure
dont on ne pourrait rien conclure (§19).

Pourquoi cette distinction est le cœur du sujet
-----------------------------------------------
Un banc d'essai qui échoue quand les chiffres déplaisent finit par être réglé
pour plaire : on réduit le scénario, on retire l'écriture, on retente jusqu'à
obtenir une bonne série. La baseline décrit alors un système qui n'existe pas.
Ici, le seul verdict porte sur la mesure elle-même :

* l'application répond-elle avant et après ?
* chaque scénario déclaré s'est-il réellement exécuté à chaque niveau ?
* l'authentification a-t-elle abouti ?
* les données créées portent-elles toutes la marque synthétique ?
* y a-t-il assez d'échantillons pour que les centiles veuillent dire quelque
  chose ?
* l'horloge est-elle monotone ?
* l'environnement est-il décrit ?
* le fichier de résultat est-il complet ?

Aucun réessai
-------------
Une requête qui échoue est comptée, classée par type, et c'est tout. Réessayer
transformerait un taux d'erreur de 8 % en 0 % apparent : le défaut passerait
inaperçu, alors que c'est précisément ce que le lot D doit voir. Aucune erreur
n'est exclue de l'agrégat.

Déterminisme et unicité
-----------------------
Le **contenu** des données est tiré d'un générateur pseudo-aléatoire ensemencé
(`--seed`) : deux exécutions produisent les mêmes valeurs. Les **identifiants**,
eux, portent un espace de noms propre à l'exécution : réutiliser les mêmes
violerait les contraintes d'unicité de la base dès la deuxième exécution, et
l'on croirait à une régression de performance là où il n'y aurait qu'un conflit
de clé.

Centiles
--------
Méthode du rang le plus proche (`ceil(p/100 × n) - 1` sur la série triée), sans
interpolation. Sur des effectifs modestes, l'interpolation fabrique des valeurs
qui n'ont jamais été observées ; le rang le plus proche renvoie toujours une
mesure réelle.

Aucun appel réseau externe. Aucun secret enregistré. Aucune donnée patient
réelle — la marque synthétique est vérifiée, pas supposée.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"

RACINE = Path(__file__).resolve().parents[1]

if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Marque portée par TOUTE donnée créée par ce script. Le contrôle de validité
#: la cherche dans chaque identifiant enregistré : sans elle, on ne pourrait pas
#: distinguer un banc d'essai d'une exécution sur des données réelles.
MARQUE_SYNTHETIQUE = "G0SYNTH"

#: Vocabulaire fermé et manifestement fictif. Le contrôle de validité refuse
#: tout nom hors de cette liste : c'est ainsi qu'une donnée non synthétique se
#: détecte, plutôt qu'en faisant confiance à l'intention de l'auteur.
PRENOMS_SYNTHETIQUES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")
NOMS_SYNTHETIQUES = ("Temoin", "Fictif", "Synthetique", "Essai", "Banc", "Zero")

#: Niveaux de concurrence. 3 correspond au premier usage envisagé au CSA GR
#: Plateau (un guichet, un préleveur, un technicien).
NIVEAUX_PAR_DEFAUT = (1, 3, 5, 10)


@dataclass(frozen=True)
class Scenario:
    """Un pas du parcours mesuré. L'ordre est significatif et enregistré."""

    nom: str
    genre: str  # "read" ou "write"
    methode: str
    gabarit: str
    description: str


#: Le parcours, dans l'ordre d'exécution. Chaque itération d'un utilisateur
#: virtuel le déroule entièrement : une lecture isolée ne dit rien d'un
#: laboratoire, où lire suppose que quelqu'un a écrit juste avant.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "auth",
        "read",
        "POST",
        "/api/v1/login/access-token",
        "Authentification par mot de passe (une fois par utilisateur virtuel et par repetition)",
    ),
    Scenario(
        "patient_create",
        "write",
        "POST",
        "/api/v1/patients",
        "Creation d'un patient synthetique",
    ),
    Scenario(
        "patient_search",
        "read",
        "GET",
        "/api/v1/patients?q={terme}&limit=20",
        "Recherche patient sur l'espace de noms de l'execution",
    ),
    Scenario(
        "order_create",
        "write",
        "POST",
        "/api/v1/exam-orders",
        "Creation d'une prescription a deux examens (NFS, GE)",
    ),
    Scenario(
        "sample_create",
        "write",
        "POST",
        "/api/v1/samples",
        "Creation d'un echantillon avec code-barres",
    ),
    Scenario(
        "sample_attach",
        "write",
        "POST",
        "/api/v1/exam-orders/{order_id}/collect",
        "Rattachement de l'echantillon a la prescription",
    ),
    Scenario(
        "worklist",
        "read",
        "GET",
        "/api/v1/worklist/my",
        "File de travail de l'operateur connecte",
    ),
    Scenario(
        "order_read",
        "read",
        "GET",
        "/api/v1/exam-orders/{order_id}",
        "Consultation d'un ordre d'examen",
    ),
    Scenario(
        "result_create",
        "write",
        "POST",
        "/api/v1/results",
        "Saisie d'un resultat NFS",
    ),
    Scenario(
        "result_read",
        "read",
        "GET",
        "/api/v1/results/{result_id}",
        "Consultation d'un resultat",
    ),
    Scenario(
        "result_release",
        "write",
        "POST",
        "/api/v1/reports/results/{result_id}/release",
        "Liberation du compte rendu selon la configuration en vigueur",
    ),
    Scenario(
        "dashboard",
        "read",
        "GET",
        "/api/v1/stats/summary",
        "Synthese d'activite (tableau de bord)",
    ),
    Scenario(
        "invoice_create",
        "write",
        "POST",
        "/api/v1/invoices",
        "Emission d'une facture fictive (compte comptable dedie)",
    ),
    Scenario(
        "payment_create",
        "write",
        "POST",
        "/api/v1/invoices/{invoice_id}/payments",
        "Encaissement fictif soldant la facture",
    ),
)

#: Réglages dont l'état conditionne l'interprétation de la mesure. Aucun secret
#: n'y figure et il ne faut jamais en ajouter : ce bloc est publié.
CONFIGURATION_OBSERVEE = (
    "PROCESS_ROLE",
    "CACHE_BACKEND",
    # Les deux limiteurs sont enregistres parce que la mesure les desactive
    # (cf. scripts/g0_perf_overlay.yml). Une baseline qui tairait cette
    # desactivation laisserait croire que le debit publie est atteignable en
    # production depuis une seule adresse IP : il ne l'est pas.
    "RATE_LIMIT_ENABLED",
    "LOGIN_RATE_LIMIT_ENABLED",
    "REQUIRE_VALIDATION_FOR_RELEASE",
    "CSA_SYNC_ENABLED",
    "ENABLE_DH36_LISTENER",
    "ANALYZER_RAW_LISTENER_ENABLED",
    "TRUSTED_PROXY_IPS",
)


def empreinte_scenario() -> str:
    """Empreinte du parcours lui-même, indépendante de la mise en forme du fichier.

    Modifier un scénario — changer une route, en retirer un, en changer l'ordre
    — change cette valeur. C'est la preuve la plus directe qu'une baseline
    décrit bien le parcours qu'on croit avoir exécuté ; l'empreinte des fichiers
    d'entrée, elle, bougerait aussi pour un commentaire reformulé.
    """
    accumulateur = hashlib.sha256()
    for scenario in SCENARIOS:
        accumulateur.update(
            f"{scenario.nom}|{scenario.genre}|{scenario.methode}|{scenario.gabarit}\0".encode()
        )
    return accumulateur.hexdigest()


# ── Mesure ────────────────────────────────────────────────────────────────────


@dataclass
class Echantillon:
    """Une requête observée. `debut_monotone` sert au contrôle d'horloge."""

    scenario: str
    duree_ms: float
    succes: bool
    type_erreur: str | None
    debut_monotone: float


@dataclass
class Collecte:
    echantillons: list[Echantillon] = field(default_factory=list)
    identifiants: list[str] = field(default_factory=list)
    noms: set[str] = field(default_factory=set)


def _centile(valeurs: list[float], centile: float) -> float:
    """Rang le plus proche, sans interpolation — la valeur renvoyée a été observée."""
    if not valeurs:
        return 0.0
    triees = sorted(valeurs)
    rang = max(1, min(len(triees), int(-(-centile * len(triees) // 100))))
    return round(triees[rang - 1], 3)


def _statistiques(echantillons: list[Echantillon], secondes_horloge: float) -> dict[str, Any]:
    """Agrégat d'une série. Les erreurs comptent dans le débit, pas dans les latences.

    Mélanger la latence d'un 500 immédiat à celle d'une réponse utile ferait
    baisser les centiles à mesure que le système se dégrade — l'inverse de ce
    qu'on veut lire. Le taux d'erreur est publié à côté, jamais fondu dedans.
    """
    reussis = [e.duree_ms for e in echantillons if e.succes]
    erreurs = [e for e in echantillons if not e.succes]
    par_type = Counter(e.type_erreur or "inconnu" for e in erreurs)
    total = len(echantillons)
    return {
        "samples": total,
        "successes": len(reussis),
        "errors": len(erreurs),
        "error_rate": round(len(erreurs) / total, 4) if total else 0.0,
        "errors_by_type": dict(sorted(par_type.items())),
        "latency_ms": {
            "min": round(min(reussis), 3) if reussis else None,
            "mean": round(statistics.fmean(reussis), 3) if reussis else None,
            "p50": _centile(reussis, 50) if reussis else None,
            "p95": _centile(reussis, 95) if reussis else None,
            "p99": _centile(reussis, 99) if reussis else None,
            "max": round(max(reussis), 3) if reussis else None,
        },
        "throughput_rps": round(total / secondes_horloge, 3) if secondes_horloge > 0 else 0.0,
        "completed": len(reussis) > 0,
    }


class Utilisateur:
    """Un utilisateur virtuel : un client HTTP, une session, un espace de noms."""

    def __init__(
        self,
        base_url: str,
        verify: bool,
        identifiant_admin: str,
        motdepasse_admin: str,
        identifiant_compta: str,
        motdepasse_compta: str,
        prefixe: str,
        graine: int,
        collecte: Collecte,
        timeout: float,
    ) -> None:
        self.api = f"{base_url.rstrip('/')}/api/v1"
        self.client = httpx.Client(timeout=timeout, verify=verify)
        self.identifiant_admin = identifiant_admin
        self.motdepasse_admin = motdepasse_admin
        self.identifiant_compta = identifiant_compta
        self.motdepasse_compta = motdepasse_compta
        self.prefixe = prefixe
        self.alea = random.Random(graine)
        self.collecte = collecte
        self.entetes: dict[str, str] = {}
        self.entetes_compta: dict[str, str] = {}

    def fermer(self) -> None:
        self.client.close()

    def _appel(
        self,
        scenario: str,
        methode: str,
        chemin: str,
        *,
        enregistrer: bool,
        **kwargs: Any,
    ) -> httpx.Response | None:
        """Une requête, chronométrée sur une horloge monotone. Jamais de réessai."""
        debut = time.perf_counter()
        reponse: httpx.Response | None = None
        type_erreur: str | None = None
        try:
            reponse = self.client.request(methode, f"{self.api}{chemin}", **kwargs)
            succes = 200 <= reponse.status_code < 300
            if not succes:
                type_erreur = f"http_{reponse.status_code}"
        except httpx.HTTPError as exc:
            succes = False
            type_erreur = f"transport_{type(exc).__name__}"
        duree = (time.perf_counter() - debut) * 1000.0
        if enregistrer:
            self.collecte.echantillons.append(
                Echantillon(scenario, duree, succes, type_erreur, debut)
            )
        return reponse if reponse is not None and 200 <= reponse.status_code < 300 else None

    def connecter(self, *, enregistrer: bool) -> bool:
        reponse = self._appel(
            "auth",
            "POST",
            "/login/access-token",
            enregistrer=enregistrer,
            data={"username": self.identifiant_admin, "password": self.motdepasse_admin},
        )
        if reponse is None:
            return False
        self.entetes = {"Authorization": f"Bearer {reponse.json()['access_token']}"}
        reponse_compta = self._appel(
            "auth",
            "POST",
            "/login/access-token",
            enregistrer=False,
            data={"username": self.identifiant_compta, "password": self.motdepasse_compta},
        )
        if reponse_compta is not None:
            self.entetes_compta = {
                "Authorization": f"Bearer {reponse_compta.json()['access_token']}"
            }
        return True

    def iteration(self, index: int, *, enregistrer: bool) -> None:
        """Un parcours complet. Chaque pas est mesuré, les échecs n'arrêtent rien.

        Un pas qui échoue empêche mécaniquement les suivants qui en dépendent :
        ils sont alors simplement absents de la série, et le contrôle de
        validité le verra (« scénario non terminé »). Inventer un identifiant de
        repli masquerait la panne.
        """
        jeton = f"{self.prefixe}-{index:04d}"
        prenom = self.alea.choice(PRENOMS_SYNTHETIQUES)
        nom = self.alea.choice(NOMS_SYNTHETIQUES)
        self.collecte.noms.update({prenom, nom})
        self.collecte.identifiants.append(jeton)

        reponse = self._appel(
            "patient_create",
            "POST",
            "/patients",
            enregistrer=enregistrer,
            headers=self.entetes,
            json={
                "ipp_unique_id": jeton,
                "first_name": prenom,
                "last_name": nom,
                "birth_date": f"19{self.alea.randint(60, 99)}-0{self.alea.randint(1, 9)}-1{self.alea.randint(0, 8)}",
                "sex": self.alea.choice(("M", "F")),
            },
        )
        patient_id = reponse.json()["id"] if reponse is not None else None

        self._appel(
            "patient_search",
            "GET",
            f"/patients?q={self.prefixe}&limit=20",
            enregistrer=enregistrer,
            headers=self.entetes,
        )

        order_id = None
        if patient_id is not None:
            reponse = self._appel(
                "order_create",
                "POST",
                "/exam-orders",
                enregistrer=enregistrer,
                headers=self.entetes,
                json={
                    "patient_id": patient_id,
                    "prescriber": f"Dr {MARQUE_SYNTHETIQUE}",
                    # « routine » et « urgent » sont les deux seules valeurs
                    # acceptees ; « normal » repond 422. Une premiere execution
                    # l'a montre (16 refus sur ce scenario).
                    "priority": self.alea.choice(("routine", "urgent")),
                    "exams": [{"exam_code": "NFS"}, {"exam_code": "GE"}],
                },
            )
            order_id = reponse.json()["id"] if reponse is not None else None

        sample_id = None
        if patient_id is not None:
            reponse = self._appel(
                "sample_create",
                "POST",
                "/samples",
                enregistrer=enregistrer,
                headers=self.entetes,
                json={"barcode": jeton, "patient_id": patient_id, "status": "Recu"},
            )
            sample_id = reponse.json()["id"] if reponse is not None else None

        if order_id is not None and sample_id is not None:
            self._appel(
                "sample_attach",
                "POST",
                f"/exam-orders/{order_id}/collect",
                enregistrer=enregistrer,
                headers=self.entetes,
                json={"barcode": jeton},
            )

        self._appel(
            "worklist", "GET", "/worklist/my", enregistrer=enregistrer, headers=self.entetes
        )

        if order_id is not None:
            self._appel(
                "order_read",
                "GET",
                f"/exam-orders/{order_id}",
                enregistrer=enregistrer,
                headers=self.entetes,
            )

        result_id = None
        if sample_id is not None:
            reponse = self._appel(
                "result_create",
                "POST",
                "/results",
                enregistrer=enregistrer,
                headers=self.entetes,
                json={
                    "sample_id": sample_id,
                    "exam_code": "NFS",
                    "data_points": {"WBC": round(self.alea.uniform(3.0, 12.0), 2)},
                },
            )
            result_id = reponse.json()["id"] if reponse is not None else None

        if result_id is not None:
            self._appel(
                "result_read",
                "GET",
                f"/results/{result_id}",
                enregistrer=enregistrer,
                headers=self.entetes,
            )
            self._appel(
                "result_release",
                "POST",
                f"/reports/results/{result_id}/release",
                enregistrer=enregistrer,
                headers=self.entetes,
                # Corps explicite : l'endpoint attend un `ReportReleaseCreate`,
                # et une requete sans corps repond 422. Une premiere execution
                # a produit 100 % d'erreurs sur ce scenario pour cette raison.
                json={"audience": "clinician"},
            )

        self._appel(
            "dashboard", "GET", "/stats/summary", enregistrer=enregistrer, headers=self.entetes
        )

        entetes_facture = self.entetes_compta or self.entetes
        reponse = self._appel(
            "invoice_create",
            "POST",
            "/invoices",
            enregistrer=enregistrer,
            headers=entetes_facture,
            json={
                "patient_label": f"{prenom} {nom} {MARQUE_SYNTHETIQUE}",
                "patient_type": "UNINSURED",
                "lines": [
                    {
                        "exam_code": "NFS",
                        "label": "Numeration",
                        "quantity": 1,
                        "unit_price_xof": "5000",
                    }
                ],
            },
        )
        if reponse is not None:
            invoice_id = reponse.json()["id"]
            self._appel(
                "payment_create",
                "POST",
                f"/invoices/{invoice_id}/payments",
                enregistrer=enregistrer,
                headers=entetes_facture,
                json={"amount_xof": "5000"},
            )


# ── Observation de la stack ───────────────────────────────────────────────────


def _docker(*arguments: str, timeout: int = 60) -> str:
    """Un appel docker, sans shell. Renvoie la sortie, ou "" en cas d'echec."""
    binaire = shutil.which("docker")
    if binaire is None:
        return ""
    try:
        acheve = subprocess.run(  # noqa: S603 - arguments litteraux, jamais de shell
            [binaire, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return acheve.stdout.strip() if acheve.returncode == 0 else ""


def _conteneur(service: str) -> str:
    """L'identifiant du conteneur d'un service Compose, ou "" s'il n'existe pas."""
    lignes = _docker("compose", "ps", "-q", service).splitlines()
    return lignes[0] if lignes else ""


def _stats_conteneurs(services: dict[str, str]) -> dict[str, Any]:
    """CPU et mémoire instantanés, par service. `docker stats` sans flux."""
    identifiants = [cid for cid in services.values() if cid]
    if not identifiants:
        return {}
    brut = _docker("stats", "--no-stream", "--format", "{{json .}}", *identifiants)
    par_id: dict[str, dict[str, Any]] = {}
    for ligne in brut.splitlines():
        try:
            enregistrement = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        par_id[str(enregistrement.get("ID", ""))[:12]] = enregistrement
    resultat: dict[str, Any] = {}
    for service, cid in services.items():
        enregistrement = par_id.get(cid[:12])
        if enregistrement is None:
            continue
        resultat[service] = {
            "cpu_percent": enregistrement.get("CPUPerc"),
            "memory_usage": enregistrement.get("MemUsage"),
            "memory_percent": enregistrement.get("MemPerc"),
            "pids": enregistrement.get("PIDs"),
        }
    return resultat


def _psql(base: str, requete: str) -> str:
    return _docker(
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "ruggylab",
        "-d",
        base,
        "-t",
        "-A",
        "-F",
        "|",
        "-c",
        requete,
    )


def _etat_postgres(base: str) -> dict[str, Any]:
    brut = _psql(
        base,
        "SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit "
        f"FROM pg_stat_database WHERE datname = '{base}'",
    )
    champs = brut.split("|") if brut else []
    if len(champs) != 5:
        return {"available": False, "reason": "pg_stat_database illisible"}
    return {
        "available": True,
        "connections": int(champs[0]),
        "xact_commit": int(champs[1]),
        "xact_rollback": int(champs[2]),
        "blocks_read": int(champs[3]),
        "blocks_hit": int(champs[4]),
    }


def _etat_valkey() -> dict[str, Any]:
    brut = _docker("compose", "exec", "-T", "valkey", "valkey-cli", "info")
    if not brut:
        return {"available": False, "reason": "valkey-cli injoignable"}
    valeurs: dict[str, str] = {}
    for ligne in brut.splitlines():
        if ":" in ligne and not ligne.startswith("#"):
            cle, _, valeur = ligne.partition(":")
            valeurs[cle.strip()] = valeur.strip()
    taille = _docker("compose", "exec", "-T", "valkey", "valkey-cli", "dbsize")
    return {
        "available": True,
        "version": valeurs.get("redis_version"),
        "used_memory_bytes": int(valeurs.get("used_memory", 0) or 0),
        "used_memory_human": valeurs.get("used_memory_human"),
        "connected_clients": int(valeurs.get("connected_clients", 0) or 0),
        "blocked_clients": int(valeurs.get("blocked_clients", 0) or 0),
        "total_commands_processed": int(valeurs.get("total_commands_processed", 0) or 0),
        "keyspace_size": int(taille or 0) if taille.isdigit() else None,
    }


def observer(base: str) -> dict[str, Any]:
    """Un instantané de la stack. Chaque source dit si elle a répondu."""
    services = {
        nom: _conteneur(nom)
        for nom in ("app", "postgres", "valkey", "proxy", "scheduler", "prometheus")
    }
    return {
        "sampled_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "containers": _stats_conteneurs(services),
        "postgres": _etat_postgres(base),
        "valkey": _etat_valkey(),
    }


def activer_journal_requetes_lentes(seuil_ms: int) -> dict[str, Any]:
    """Journalise les requêtes au-delà d'un seuil, sur le conteneur jetable seul.

    `ALTER SYSTEM` n'écrit que dans le `postgresql.auto.conf` du conteneur de
    mesure, détruit à la fin. Aucun fichier du dépôt n'est touché : modifier
    `docker-compose.yml` aurait changé l'empreinte d'entrée du lot A pour un
    réglage d'observation.
    """
    sortie = _psql("postgres", f"ALTER SYSTEM SET log_min_duration_statement = '{seuil_ms}ms'")
    rechargement = _psql("postgres", "SELECT pg_reload_conf()")
    actif = rechargement.strip().lower() in ("t", "true")
    return {
        "enabled": actif,
        "threshold_ms": seuil_ms,
        "detail": None if actif else (sortie or "ALTER SYSTEM refuse"),
    }


def relever_requetes_lentes(seuil_ms: int, actif: bool) -> dict[str, Any]:
    """Les requêtes lentes journalisées pendant la mesure, ou pourquoi il n'y en a pas."""
    if not actif:
        return {
            "available": False,
            "reason": "journalisation des requetes lentes non activable sur ce conteneur",
            "threshold_ms": seuil_ms,
            "count": None,
        }
    journal = _docker("compose", "logs", "--no-color", "--tail", "5000", "postgres")
    lignes = [ligne for ligne in journal.splitlines() if "duration:" in ligne]
    return {
        "available": True,
        "threshold_ms": seuil_ms,
        "count": len(lignes),
        "examples": [ligne[-300:] for ligne in lignes[:10]],
    }


#: Interrupteurs dont l'état conditionne la validité même de la mesure : chacun
#: ouvrirait une conversation avec un système extérieur au banc d'essai (le
#: dossier patient CSA, un automate). Lire la variable d'environnement ne suffit
#: pas — absente, elle ne dit pas « false », elle ne dit rien, et la valeur
#: effective est celle que le code choisit par défaut.
INTERRUPTEURS_EXTERNES = (
    "CSA_SYNC_ENABLED",
    "ENABLE_DH36_LISTENER",
    "ANALYZER_RAW_LISTENER_ENABLED",
)


def reglages_effectifs() -> dict[str, Any]:
    """Ce que l'application applique réellement, demandé à l'application.

    `docker compose exec app env` ne montre que les variables *transmises* : un
    interrupteur non transmis y apparaît absent, ce qui est indiscernable d'un
    interrupteur absent parce que désactivé — et indiscernable, aussi, d'un
    défaut de code qui l'aurait activé. La question est donc posée au processus
    qui décide, dans le conteneur mesuré.
    """
    sortie = _docker(
        "compose",
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        (
            "import json;from app.core.config import settings;"
            "print(json.dumps({n: bool(getattr(settings, n)) for n in "
            f"{list(INTERRUPTEURS_EXTERNES)!r}" + "}))"
        ),
    )
    try:
        valeurs = json.loads(sortie.splitlines()[-1]) if sortie else None
    except (json.JSONDecodeError, IndexError):
        valeurs = None
    if not isinstance(valeurs, dict):
        return {"available": False, "reason": "reglages effectifs illisibles"}
    return {"available": True, "settings": valeurs}


def decrire_environnement(
    *,
    base: str,
    image: str,
    image_archive_sha256: str | None,
    runner: str,
    git_commit: str,
) -> dict[str, Any]:
    """L'environnement de mesure. Un chiffre sans environnement ne veut rien dire."""
    try:
        import psutil

        memoire_totale = int(psutil.virtual_memory().total)
        memoire_disponible = int(psutil.virtual_memory().available)
    except Exception:  # noqa: BLE001 - psutil absent ou refuse : on le dit, on n'invente pas
        memoire_totale = memoire_disponible = 0

    version_postgres = _psql(base, "SELECT version()").split(" on ")[0] or None
    valkey = _etat_valkey()
    configuration: dict[str, str | None] = {}
    brut = _docker("compose", "exec", "-T", "app", "env")
    variables = dict(ligne.split("=", 1) for ligne in brut.splitlines() if "=" in ligne)
    for cle in CONFIGURATION_OBSERVEE:
        configuration[cle] = variables.get(cle)

    return {
        "git_commit": git_commit,
        "runner": runner,
        "os": f"{platform.system()} {platform.release()}",
        "platform": f"{platform.system().lower()}/{platform.machine().lower()}",
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": memoire_totale,
        "memory_available_bytes": memoire_disponible,
        "python_version": platform.python_version(),
        "docker_version": _docker("version", "--format", "{{.Server.Version}}") or None,
        "compose_project": os.environ.get("COMPOSE_PROJECT_NAME"),
        "image_reference": image,
        "image_id": _docker("image", "inspect", image, "--format", "{{.Id}}") or None,
        "image_archive_sha256": image_archive_sha256,
        "postgres_version": version_postgres,
        "valkey_version": valkey.get("version"),
        "application_configuration": configuration,
        "application_configuration_note": (
            "null = variable non transmise au conteneur ; la valeur effective est "
            "alors le defaut du code, publie dans effective_external_switches"
        ),
        "effective_external_switches": reglages_effectifs(),
        "external_network_calls": False,
    }


# ── Exécution ─────────────────────────────────────────────────────────────────


def executer(args: argparse.Namespace) -> dict[str, Any]:
    """Le banc d'essai complet. Renvoie le corps de `perf-baseline.json`."""
    verify = not args.insecure
    api = f"{args.base_url.rstrip('/')}/api/v1"
    run_id = uuid.uuid4().hex[:10]
    depart = time.time()
    debut_monotone = time.perf_counter()

    client = httpx.Client(timeout=args.timeout, verify=verify)
    try:
        sain_avant = client.get(f"{api}/health").status_code == 200
    except httpx.HTTPError:
        sain_avant = False

    # Compte comptable dédié : la facturation est cloisonnée, un administrateur
    # n'y accède pas. Le créer ici plutôt que dans la boucle évite de mesurer
    # une création d'utilisateur en la faisant passer pour une facturation.
    compta = f"{MARQUE_SYNTHETIQUE.lower()}_compta_{run_id}"
    motdepasse_compta = "G0Synth!Compta2026"
    if sain_avant:
        reponse = client.post(
            f"{api}/login/access-token",
            data={"username": args.admin_user, "password": args.admin_password},
        )
        if reponse.status_code == 200:
            client.post(
                f"{api}/users",
                headers={"Authorization": f"Bearer {reponse.json()['access_token']}"},
                json={
                    "username": compta,
                    "password": motdepasse_compta,
                    "role": "accountant",
                },
            )
    client.close()

    journal_lent = activer_journal_requetes_lentes(args.slow_query_threshold_ms)

    niveaux: dict[str, Any] = {}
    collecte_globale = Collecte()

    for niveau in args.concurrency:
        series_repetitions: list[dict[str, Any]] = []
        echantillons_niveau: list[Echantillon] = []
        avant = observer(args.database_name)
        horloge_niveau = 0.0

        for repetition in range(args.repetitions):
            collecte = Collecte()
            utilisateurs = [
                Utilisateur(
                    args.base_url,
                    verify,
                    args.admin_user,
                    args.admin_password,
                    compta,
                    motdepasse_compta,
                    f"{MARQUE_SYNTHETIQUE}-{run_id}-L{niveau}-R{repetition}-W{indice}",
                    args.seed + niveau * 1000 + repetition * 100 + indice,
                    collecte,
                    args.timeout,
                )
                for indice in range(niveau)
            ]

            def travail(utilisateur: Utilisateur) -> None:
                # L'authentification de mise en route n'est pas mesuree : elle
                # amorce les connexions TLS et le cache, et son cout ne dit rien
                # du regime etabli.
                utilisateur.connecter(enregistrer=False)
                for index in range(args.warmup):
                    utilisateur.iteration(index, enregistrer=False)
                # Chaque iteration mesuree commence par une authentification.
                # Ne la mesurer qu'une fois par utilisateur donnait trois
                # echantillons au niveau 1 : un p99 sur trois valeurs ne
                # signifie rien, et le controle d'effectif le refusait a juste
                # titre. Ouvrir une session par parcours reste realiste — le
                # personnel du laboratoire se connecte plusieurs fois par jour.
                for index in range(args.iterations):
                    utilisateur.connecter(enregistrer=True)
                    utilisateur.iteration(args.warmup + index, enregistrer=True)

            debut_repetition = time.perf_counter()
            with ThreadPoolExecutor(max_workers=niveau) as executeur:
                list(executeur.map(travail, utilisateurs))
            duree_repetition = time.perf_counter() - debut_repetition
            for utilisateur in utilisateurs:
                utilisateur.fermer()

            horloge_niveau += duree_repetition
            echantillons_niveau.extend(collecte.echantillons)
            collecte_globale.echantillons.extend(collecte.echantillons)
            collecte_globale.identifiants.extend(collecte.identifiants)
            collecte_globale.noms.update(collecte.noms)
            series_repetitions.append(
                {
                    "index": repetition,
                    "wall_clock_seconds": round(duree_repetition, 3),
                    "samples": len(collecte.echantillons),
                    "errors": sum(1 for e in collecte.echantillons if not e.succes),
                }
            )

        apres = observer(args.database_name)
        par_scenario = {
            scenario.nom: _statistiques(
                [e for e in echantillons_niveau if e.scenario == scenario.nom],
                horloge_niveau,
            )
            for scenario in SCENARIOS
        }
        niveaux[str(niveau)] = {
            "concurrency": niveau,
            "repetitions": series_repetitions,
            "wall_clock_seconds": round(horloge_niveau, 3),
            "scenarios": par_scenario,
            "aggregate": _statistiques(echantillons_niveau, horloge_niveau),
            "resources": {
                "before": avant,
                "after": apres,
                "postgres_delta": _delta_postgres(avant, apres),
            },
        }

    duree_totale = time.perf_counter() - debut_monotone
    client = httpx.Client(timeout=args.timeout, verify=verify)
    try:
        sain_apres = client.get(f"{api}/health").status_code == 200
    except httpx.HTTPError:
        sain_apres = False
    client.close()

    erreurs_totales = Counter(
        e.type_erreur or "inconnu" for e in collecte_globale.echantillons if not e.succes
    )
    # Monotonie de l'horloge. Comparer l'ordre des echantillons dans la liste
    # ne teste PAS l'horloge : plusieurs fils y ajoutent en concurrence, et les
    # arrivees se croisent legitimement. La premiere version de ce controle
    # echouait pour cette raison — il declarait « horloge non monotone » un
    # simple entrelacement de fils.
    #
    # Ce qui est verifie ici est ce qui compte reellement : aucune duree
    # negative ou nulle, aucun depart anterieur au debut de l'execution, et une
    # serie de lectures de `time.perf_counter()` qui ne recule jamais.
    lectures = [time.perf_counter() for _ in range(64)]
    horloge_monotone = (
        all(e.duree_ms > 0 for e in collecte_globale.echantillons)
        and all(e.debut_monotone >= debut_monotone for e in collecte_globale.echantillons)
        and all(a <= b for a, b in zip(lectures, lectures[1:], strict=False))
    )

    corps = {
        "_comment": (
            "Constat, pas verdict. Une latence elevee est un resultat ; seule une "
            "mesure invalide fait echouer ce script. Aucun reessai, aucune erreur "
            "exclue de l'agregat."
        ),
        "run": {
            "run_id": run_id,
            "seed": args.seed,
            "started_at": datetime.fromtimestamp(depart, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duree_totale, 3),
            "concurrency_levels": list(args.concurrency),
            "repetitions": args.repetitions,
            "iterations_per_worker": args.iterations,
            "warmup_iterations_per_worker": args.warmup,
            "scenario_order": [s.nom for s in SCENARIOS],
            "scenario_sha256": empreinte_scenario(),
            "percentile_method": "nearest-rank (ceil(p/100*n)) sans interpolation",
            "clock_source": "time.perf_counter (monotone)",
            "clock_monotonic": horloge_monotone,
            "retries": 0,
            "command": args.command,
            "base_url_scheme": args.base_url.split(":")[0],
        },
        "scenarios": [
            {
                "name": s.nom,
                "kind": s.genre,
                "method": s.methode,
                "path_template": s.gabarit,
                "description": s.description,
            }
            for s in SCENARIOS
        ],
        "dataset": {
            "synthetic_marker": MARQUE_SYNTHETIQUE,
            "identifier_prefix": f"{MARQUE_SYNTHETIQUE}-{run_id}",
            "name_vocabulary": sorted(PRENOMS_SYNTHETIQUES + NOMS_SYNTHETIQUES),
            "names_used": sorted(collecte_globale.noms),
            "identifiers_created": len(collecte_globale.identifiants),
            "sample_identifiers": collecte_globale.identifiants[:5]
            + collecte_globale.identifiants[-5:],
            "all_identifiers_prefixed": all(
                i.startswith(MARQUE_SYNTHETIQUE) for i in collecte_globale.identifiants
            ),
            "source": "genere par scripts/g0_perf_baseline.py ; aucune donnee patient reelle",
        },
        "application_health": {"before": sain_avant, "after": sain_apres},
        "levels": niveaux,
        "errors_by_type_total": dict(sorted(erreurs_totales.items())),
        "slow_queries": relever_requetes_lentes(
            args.slow_query_threshold_ms, journal_lent["enabled"]
        ),
        "environment": decrire_environnement(
            base=args.database_name,
            image=args.image,
            image_archive_sha256=args.image_archive_sha256,
            runner=args.runner,
            git_commit=args.git_commit,
        ),
        "validity_policy": {
            "min_samples_per_scenario_per_level": args.min_samples,
            "note": (
                "Aucun seuil de latence. Les controles portent sur la validite de "
                "la mesure, jamais sur la valeur mesuree."
            ),
        },
    }
    return corps


def _delta_postgres(avant: dict[str, Any], apres: dict[str, Any]) -> dict[str, Any]:
    a, b = avant.get("postgres", {}), apres.get("postgres", {})
    if not (a.get("available") and b.get("available")):
        return {"available": False}
    return {
        "available": True,
        "xact_commit": b["xact_commit"] - a["xact_commit"],
        "xact_rollback": b["xact_rollback"] - a["xact_rollback"],
        "blocks_read": b["blocks_read"] - a["blocks_read"],
        "blocks_hit": b["blocks_hit"] - a["blocks_hit"],
    }


# ── Validité (§19) ────────────────────────────────────────────────────────────


def valider(corps: Any) -> list[str]:
    """Les motifs d'invalidité d'une mesure. Vide si la mesure est exploitable.

    Aucun de ces contrôles ne porte sur la valeur des latences. Tous portent sur
    la capacité à conclure quoi que ce soit du fichier.
    """
    motifs: list[str] = []
    if not isinstance(corps, dict):
        return ["resultat illisible"]

    execution = corps.get("run") or {}
    sante = corps.get("application_health") or {}
    jeu = corps.get("dataset") or {}
    environnement = corps.get("environment") or {}
    niveaux = corps.get("levels") or {}
    politique = corps.get("validity_policy") or {}
    minimum = int(politique.get("min_samples_per_scenario_per_level") or 0)

    # 1. Application saine avant et après.
    if not sante.get("before"):
        motifs.append("application non saine avant la mesure")
    if not sante.get("after"):
        motifs.append("application non saine apres la mesure")

    # 2. Fichier complet : champs d'execution obligatoires.
    for cle in (
        "run_id",
        "seed",
        "concurrency_levels",
        "repetitions",
        "iterations_per_worker",
        "scenario_order",
        "scenario_sha256",
        "duration_seconds",
        "command",
    ):
        if execution.get(cle) in (None, "", [], {}):
            motifs.append(f"fichier de resultat incomplet : run.{cle} absent")

    # 3. Horloge monotone.
    if execution.get("clock_monotonic") is not True:
        motifs.append("horloge non monotone : les durees ne sont pas comparables")

    # 4. Environnement decrit — chaque champ, faute de quoi la mesure ne se
    #    rejoue pas et ne se compare a rien.
    for cle in (
        "git_commit",
        "runner",
        "os",
        "architecture",
        "cpu_count",
        "memory_total_bytes",
        "python_version",
        "docker_version",
        "image_id",
        "postgres_version",
        "valkey_version",
        "application_configuration",
    ):
        if environnement.get(cle) in (None, "", 0, {}):
            motifs.append(f"environnement non decrit : {cle} absent")

    # 4 bis. Aucun systeme externe. Un interrupteur ouvert ferait sortir des
    #        donnees du banc d'essai et melerait la latence d'un tiers a la
    #        mesure : ce ne serait plus le laboratoire qu'on mesure.
    interrupteurs = environnement.get("effective_external_switches") or {}
    if not interrupteurs.get("available"):
        motifs.append(
            "reglages effectifs non lus : impossible d'affirmer qu'aucun systeme "
            "externe n'a participe a la mesure"
        )
    else:
        for nom, valeur in (interrupteurs.get("settings") or {}).items():
            if valeur:
                motifs.append(f"systeme externe actif pendant la mesure : {nom} = true")
        absents = [
            n for n in INTERRUPTEURS_EXTERNES if n not in (interrupteurs.get("settings") or {})
        ]
        if absents:
            motifs.append(f"interrupteurs externes non verifies : {absents}")

    # 5. Donnees synthetiques : verifiees, pas supposees.
    marque = jeu.get("synthetic_marker")
    if marque != MARQUE_SYNTHETIQUE:
        motifs.append(f"marque synthetique absente ou alteree : {marque!r}")
    if not jeu.get("all_identifiers_prefixed"):
        motifs.append("des identifiants ne portent pas la marque synthetique")
    for identifiant in jeu.get("sample_identifiers") or []:
        if not str(identifiant).startswith(str(marque)):
            motifs.append(f"identifiant non synthetique detecte : {identifiant!r}")
    vocabulaire = set(jeu.get("name_vocabulary") or [])
    if vocabulaire != set(PRENOMS_SYNTHETIQUES + NOMS_SYNTHETIQUES):
        motifs.append("vocabulaire synthetique altere")
    hors_vocabulaire = [n for n in (jeu.get("names_used") or []) if n not in vocabulaire]
    if hors_vocabulaire:
        motifs.append(f"noms hors vocabulaire synthetique : {hors_vocabulaire}")
    if not jeu.get("identifiers_created"):
        motifs.append("aucune donnee synthetique creee : le scenario n'a rien ecrit")

    # 6. Les niveaux demandes ont-ils tous ete mesures ?
    attendus = [str(n) for n in (execution.get("concurrency_levels") or [])]
    manquants = [n for n in attendus if n not in niveaux]
    if manquants:
        motifs.append(f"niveaux de concurrence non mesures : {manquants}")
    if int(execution.get("repetitions") or 0) < 3:
        motifs.append("moins de trois repetitions : la dispersion n'est pas observable")

    # 7. Chaque scenario declare s'est-il termine, avec assez d'echantillons ?
    declares = execution.get("scenario_order") or []
    for nom_niveau, niveau in niveaux.items():
        scenarios = niveau.get("scenarios") or {}
        repetitions = niveau.get("repetitions") or []
        if len(repetitions) < int(execution.get("repetitions") or 0):
            motifs.append(f"niveau {nom_niveau} : repetitions manquantes")
        for nom in declares:
            mesure = scenarios.get(nom)
            if mesure is None:
                motifs.append(f"niveau {nom_niveau} : scenario `{nom}` absent du resultat")
                continue
            if not mesure.get("completed"):
                motifs.append(
                    f"niveau {nom_niveau} : scenario `{nom}` non termine "
                    f"(aucune reponse en succes sur {mesure.get('samples')} tentatives)"
                )
            if int(mesure.get("samples") or 0) < minimum:
                motifs.append(
                    f"niveau {nom_niveau} : scenario `{nom}` sous-echantillonne "
                    f"({mesure.get('samples')} < {minimum})"
                )
            latences = mesure.get("latency_ms") or {}
            for centile in ("p50", "p95", "p99", "mean", "max"):
                if latences.get(centile) is None:
                    motifs.append(f"niveau {nom_niveau} : scenario `{nom}` sans {centile}")
        agregat = niveau.get("aggregate") or {}
        if agregat.get("throughput_rps") in (None, 0.0):
            motifs.append(f"niveau {nom_niveau} : debit absent ou nul")
        if (agregat.get("latency_ms") or {}).get("p99") is None:
            motifs.append(f"niveau {nom_niveau} : agregat sans p99")

    # 8. Coherence interne des erreurs. Un taux d'erreur se mesure et se
    #    publie ; il ne se rattrape ni par un reessai ni par une soustraction.
    #    Si l'agregat d'un niveau annonce moins d'erreurs que la somme de ses
    #    scenarios, une erreur a ete effacee quelque part entre la mesure et le
    #    fichier — et c'est exactement ce que le lot D ne verrait plus.
    total_declare = 0
    for nom_niveau, niveau in niveaux.items():
        scenarios = niveau.get("scenarios") or {}
        agregat = niveau.get("aggregate") or {}
        somme = sum(int((s or {}).get("errors") or 0) for s in scenarios.values())
        if int(agregat.get("errors") or 0) != somme:
            motifs.append(
                f"niveau {nom_niveau} : agregat a {agregat.get('errors')} erreur(s) "
                f"contre {somme} dans le detail par scenario — une erreur a ete masquee"
            )
        echantillons = sum(int((s or {}).get("samples") or 0) for s in scenarios.values())
        if int(agregat.get("samples") or 0) != echantillons:
            motifs.append(
                f"niveau {nom_niveau} : agregat a {agregat.get('samples')} echantillons "
                f"contre {echantillons} dans le detail par scenario"
            )
        total_declare += somme
    total_publie = sum(int(v) for v in (corps.get("errors_by_type_total") or {}).values())
    if niveaux and total_publie != total_declare:
        motifs.append(
            f"errors_by_type_total totalise {total_publie} erreur(s) contre "
            f"{total_declare} dans les niveaux — la classification est incomplete"
        )

    if execution.get("retries") != 0:
        motifs.append("des reessais ont eu lieu : le taux d'erreur publie est sous-estime")

    if minimum <= 0:
        motifs.append("politique de validite absente : aucun minimum d'echantillons declare")

    return motifs


def valider_provenance(entete: Any, corps: Any) -> list[str]:
    """La provenance decrit-elle la mesure qu'elle accompagne ?

    Rien ici ne compare des latences : elles varient par nature, et les
    comparer octet a octet ferait echouer toute execution honnete. Ce qui est
    verifie est la **coherence** — schema, completude, et surtout que
    l'empreinte du scenario enregistree est bien celle du scenario que le code
    execute aujourd'hui. Sans ce dernier controle, on pourrait changer une
    route mesuree et republier une provenance qui decrit l'ancien parcours.
    """
    motifs: list[str] = []
    if not isinstance(entete, dict):
        return ["provenance illisible"]
    deterministe = entete.get("deterministic")
    volatile = entete.get("volatile")
    if not isinstance(deterministe, dict):
        return ["provenance sans bloc `deterministic`"]
    if not isinstance(volatile, dict):
        motifs.append("provenance sans bloc `volatile`")
        volatile = {}

    for cle in (
        "schema_version",
        "generator_version",
        "generation_command",
        "baseline_input_commit",
        "baseline_input_ref",
        "relevant_input_set",
        "relevant_input_patterns",
        "relevant_input_file_count",
        "relevant_input_tree_sha256",
        "scenario_sha256",
        "scenario_order",
        "concurrency_levels",
        "repetitions",
        "iterations_per_worker",
        "seed",
    ):
        if deterministe.get(cle) in (None, "", [], {}):
            motifs.append(f"provenance incomplete : deterministic.{cle} absent")

    empreinte = str(deterministe.get("relevant_input_tree_sha256") or "")
    if len(empreinte) != 64 or any(c not in "0123456789abcdef" for c in empreinte):
        motifs.append("provenance : relevant_input_tree_sha256 n'est pas une empreinte SHA-256")
    if deterministe.get("relevant_input_set") != "performance":
        motifs.append(
            f"provenance : ensemble d'entree {deterministe.get('relevant_input_set')!r}, "
            "attendu 'performance'"
        )
    if str(deterministe.get("baseline_input_ref") or "").startswith(("tmp/", "wip/")):
        motifs.append("provenance : reference temporaire inscrite comme source")

    if deterministe.get("scenario_sha256") != empreinte_scenario():
        motifs.append(
            "provenance : l'empreinte du scenario enregistree "
            f"({deterministe.get('scenario_sha256')}) n'est pas celle du scenario "
            f"execute par ce code ({empreinte_scenario()})"
        )

    for cle in ("git_commit", "runner", "os", "docker_version", "image_id"):
        if not (volatile.get("environment") or {}).get(cle):
            motifs.append(f"provenance : environnement incomplet ({cle} absent)")

    if isinstance(corps, dict):
        execution = corps.get("run") or {}
        for cle in (
            "scenario_sha256",
            "scenario_order",
            "concurrency_levels",
            "repetitions",
            "iterations_per_worker",
            "seed",
        ):
            if deterministe.get(cle) != execution.get(cle):
                motifs.append(
                    f"provenance incoherente : {cle} = {deterministe.get(cle)!r} "
                    f"cote provenance, {execution.get(cle)!r} cote mesure"
                )
        if (volatile.get("environment") or {}) != (corps.get("environment") or {}):
            motifs.append("provenance incoherente : environnement different de celui de la mesure")

    return motifs


# ── Sortie ────────────────────────────────────────────────────────────────────


def _ecrire(chemin: Path, contenu: dict[str, Any]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(contenu, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def construire_provenance(corps: dict[str, Any], commande: str) -> dict[str, Any]:
    """La provenance de la mesure (§20), empreinte du scenario comprise."""
    from scripts.g0_provenance import provenance

    entete = provenance(
        "performance",
        commande,
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
    )
    entete["deterministic"]["scenario_sha256"] = corps["run"]["scenario_sha256"]
    entete["deterministic"]["scenario_order"] = corps["run"]["scenario_order"]
    entete["deterministic"]["concurrency_levels"] = corps["run"]["concurrency_levels"]
    entete["deterministic"]["repetitions"] = corps["run"]["repetitions"]
    entete["deterministic"]["iterations_per_worker"] = corps["run"]["iterations_per_worker"]
    entete["deterministic"]["seed"] = corps["run"]["seed"]
    # `volatile` porte ce qui varie d'une execution a l'autre : l'environnement
    # et la duree. Le comparer octet a octet ferait echouer tout controle, et
    # comparer des latences n'aurait aucun sens — elles varient par nature.
    entete["volatile"]["environment"] = corps["environment"]
    entete["volatile"]["run_id"] = corps["run"]["run_id"]
    entete["volatile"]["duration_seconds"] = corps["run"]["duration_seconds"]
    entete["volatile"]["dataset"] = {
        cle: corps["dataset"][cle]
        for cle in ("synthetic_marker", "identifier_prefix", "identifiers_created", "source")
    }
    return entete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://localhost")
    parser.add_argument("--insecure", action="store_true", help="certificat auto-signe (proxy CI)")
    parser.add_argument("--admin-user", default=os.environ.get("G0_ADMIN_USER", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("G0_ADMIN_PASSWORD", ""))
    parser.add_argument("--seed", type=int, default=20260909)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--slow-query-threshold-ms", type=int, default=200)
    parser.add_argument(
        "--concurrency",
        type=lambda v: [int(x) for x in v.split(",")],
        default=list(NIVEAUX_PAR_DEFAUT),
    )
    parser.add_argument("--database-name", default="ruggylab")
    parser.add_argument("--image", default=os.environ.get("RUGGYLAB_IMAGE", "ruggylab-os:g0"))
    parser.add_argument("--image-archive-sha256", default=None)
    parser.add_argument("--runner", default=os.environ.get("G0_RUNNER", platform.node()))
    parser.add_argument("--git-commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output-dir", type=Path, default=RACINE / "artifacts" / "g0")
    parser.add_argument("--run", action="store_true", help="executer la mesure")
    parser.add_argument(
        "--validate",
        type=Path,
        default=None,
        help="controler la validite d'un perf-baseline.json existant",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=None,
        help="perf-provenance.json a controler avec --validate (schema, completude, coherence)",
    )
    parser.add_argument("--print-scenario-sha256", action="store_true")
    args = parser.parse_args(argv)

    if args.print_scenario_sha256:
        print(empreinte_scenario())
        if not (args.run or args.validate):
            return 0

    if args.validate is not None:
        try:
            fichier = json.loads(args.validate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ECHEC : {args.validate} illisible ({exc})", file=sys.stderr)
            return 1
        corps = fichier.get("payload")
        if corps is None:
            print(f"ECHEC : {args.validate} sans bloc `payload`", file=sys.stderr)
            return 1
        motifs = valider(corps)
        if args.provenance is not None:
            try:
                entete = json.loads(args.provenance.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                motifs.append(f"provenance illisible : {exc}")
            else:
                motifs.extend(valider_provenance(entete, corps))
        else:
            motifs.append(
                "provenance non fournie : --provenance est obligatoire avec "
                "--validate, sans quoi le controle porterait sur des chiffres "
                "dont on ignore la provenance"
            )
        if motifs:
            print("\nECHEC : mesure de performance INVALIDE.", file=sys.stderr)
            for motif in motifs:
                print(f"  ! {motif}", file=sys.stderr)
            return 1
        print("Mesure de performance : valide (les latences ne sont pas jugees ici).")
        return 0

    if not args.run:
        parser.error("choisir --run, --validate ou --print-scenario-sha256")

    if not args.admin_password:
        print("ECHEC : mot de passe administrateur absent (--admin-password)", file=sys.stderr)
        return 1

    args.command = " ".join(
        [
            "python scripts/g0_perf_baseline.py --run",
            f"--base-url {args.base_url}",
            f"--concurrency {','.join(str(n) for n in args.concurrency)}",
            f"--repetitions {args.repetitions}",
            f"--iterations {args.iterations}",
            f"--warmup {args.warmup}",
            f"--seed {args.seed}",
        ]
    )

    corps = executer(args)
    motifs = valider(corps)
    entete = construire_provenance(corps, args.command)
    motifs.extend(valider_provenance(entete, corps))
    corps["validity"] = {
        "valid": not motifs,
        "failures": motifs,
        "checked_by": "scripts/g0_perf_baseline.py valider()",
    }

    _ecrire(
        args.output_dir / "perf-baseline.json", {"schema_version": SCHEMA_VERSION, "payload": corps}
    )
    _ecrire(args.output_dir / "perf-provenance.json", entete)

    agregat_global = corps["levels"]
    print("\nBaseline de performance — resume (constat, pas verdict) :")
    for nom, niveau in agregat_global.items():
        a = niveau["aggregate"]
        latences = a["latency_ms"]
        print(
            f"  concurrence {nom:>2s} : p50 {latences['p50']} ms  p95 {latences['p95']} ms  "
            f"p99 {latences['p99']} ms  debit {a['throughput_rps']} req/s  "
            f"erreurs {a['errors']}/{a['samples']} ({a['error_rate'] * 100:.2f} %)"
        )
    print(f"\nArtefacts ecrits dans {args.output_dir}")

    if motifs:
        print("\nECHEC : mesure de performance INVALIDE.", file=sys.stderr)
        for motif in motifs:
            print(f"  ! {motif}", file=sys.stderr)
        return 1
    print("Mesure valide.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

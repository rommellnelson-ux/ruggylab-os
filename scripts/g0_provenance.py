"""Provenance des artefacts G0 — dire de quoi la baseline parle, et le prouver.

Un artefact d'inventaire qui ne dit pas de quel code il parle n'est pas une
preuve : on ne peut ni le rejouer, ni le contredire. La première version de ce
module enregistrait `git rev-parse HEAD` et le nom de la branche courante. Sur
une branche de travail temporaire, cela produisait ``source_git_ref =
tmp/g0-architecture-work`` et un SHA qui n'était pas celui de la baseline
annoncée — une provenance qui désignait une référence appelée à disparaître.

Deux champs distincts remplacent cette approximation.

``baseline_input_commit`` / ``baseline_input_ref``
    Le point d'entrée **déclaré** de la campagne, sur une référence permanente.
    Déclaré et non dérivé : dériver le SHA de la tête au moment de la
    génération enregistrerait la branche de travail, et enregistrer la future
    tête de la pull request créerait une dépendance circulaire — l'artefact
    citerait le commit qui le contient.

``relevant_input_tree_sha256``
    L'empreinte des **octets réellement lus**. C'est la preuve véritable :
    elle ne dépend d'aucune branche, d'aucun commit, d'aucun outil de gestion
    de version. Deux personnes qui disposent des mêmes fichiers obtiennent la
    même empreinte ; un fichier d'entrée modifié la change.

L'empreinte est **comparée par `--check`**, contrairement à l'heure de
génération. Sans cela, modifier un fichier d'entrée aurait laissé la provenance
versionnée intacte : elle aurait continué à désigner un état révolu, sans que
rien ne le signale.

Elle doit donc être **identique sur toute machine** à contenu égal. Deux pièges
ont été rencontrés et traités : les fins de ligne, qu'un dépôt cloné sous
Windows reçoit en CRLF, et l'**ordre des chemins**, que `sorted()` sur des
objets `Path` calcule casse repliée sous Windows et casse exacte sous Linux.
Le second n'a été trouvé que parce que la CI Linux a refusé une baseline
générée sous Windows dont le contenu était pourtant identique.

Aucun sous-processus, aucun appel réseau, aucun secret, aucune donnée patient.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[1]

#: Point d'entrée déclaré de la campagne G0. Une référence **permanente** :
#: jamais une branche de travail, dont le nom ne survivra pas à la fusion.
BASELINE_INPUT_COMMIT = "f7abd7e10eb8acc22e3e13775a43172e7a90261e"
BASELINE_INPUT_REF = "main"

#: Ce que chaque générateur lit réellement. Élargir cet ensemble sans raison
#: rendrait l'empreinte instable — elle changerait sur des modifications sans
#: rapport, on finirait par régénérer sans lire le diff, et le contrôle
#: perdrait son sens.
ENSEMBLES_ENTREE: dict[str, tuple[str, ...]] = {
    # L'inventaire lit le code, les migrations, les fichiers d'orchestration,
    # la définition de la CI et **les scripts d'exploitation**.
    #
    # Les scripts n'y figuraient pas. L'artefact recensait pourtant 30 scripts
    # CLI un par un : il décrivait un corps qu'il ne lisait pas. Modifier
    # `scripts/reset_admin_password.py` laissait donc l'empreinte intacte, et
    # `--check` déclarait la baseline à jour alors qu'une surface d'entrée
    # venait de changer. Le défaut a été relevé par le lot C sur le lot A ; il
    # est corrigé ici.
    #
    # Les extensions sont énumérées plutôt qu'un `scripts/**/*` global : ce
    # répertoire reçoit aussi, à l'exécution, des rapports bruts et des bases
    # jetables qu'un motif large absorberait.
    "inventory": (
        "app/**/*",
        "alembic/**/*",
        "deploy/**/*",
        "monitoring/**/*",
        "scripts/**/*.py",
        "scripts/**/*.sh",
        "scripts/**/*.ps1",
        "scripts/**/*.yml",
        "scripts/**/*.yaml",
        "scripts/**/*.json",
        "docker-compose*.yml",
        "Dockerfile",
        "requirements.txt",
        ".github/workflows/ci.yml",
    ),
    # Le schéma vient d'une base migrée : ce sont les migrations qui le
    # déterminent, et les versions d'Alembic et de SQLAlchemy qui les exécutent.
    "schema": (
        "alembic/**/*",
        "alembic.ini",
        "requirements.txt",
    ),
    # La baseline de sécurité lit le code applicatif, les artefacts du lot A
    # dont elle dérive la matrice, le registre de qualification des routes, la
    # baseline de secrets, et les fichiers qui décrivent les frontières
    # (Compose, proxy, supervision).
    #
    # Les trois artefacts du lot A sont nommés un par un, jamais par un motif
    # `artifacts/g0/*` : ce répertoire reçoit aussi les artefacts du lot B, et
    # un motif large rendrait l'empreinte auto-référentielle — elle changerait
    # à chaque génération, et le contrôle échouerait toujours.
    "security": (
        "app/**/*",
        "artifacts/g0/routes.json",
        "artifacts/g0/entrypoints.json",
        "artifacts/g0/schema.json",
        "docs/g0/ROUTE_EXPOSURE_QUALIFICATION.json",
        ".secrets.baseline",
        # Les generateurs eux-memes entrent dans l'empreinte. Le lot C a releve
        # sur le lot A le defaut inverse : un inventaire qui recense les scripts
        # sans les couvrir, donc un corps qui change sans que l'empreinte bouge.
        # Ici, modifier une regle de classification ou la barriere de secrets
        # DOIT obliger a regenerer.
        "scripts/g0_security_baseline.py",
        "scripts/g0_security_rules.py",
        "scripts/g0_secret_gate.py",
        "deploy/**/*",
        "monitoring/**/*",
        "docker-compose*.yml",
        "requirements.txt",
    ),
    # La couverture depend du code mesure, des tests qui l'executent, de la
    # configuration de pytest, des versions epinglees de l'outil de mesure et
    # du **plan de mesure** — c'est lui qui fixe les commandes, les fichiers
    # PostgreSQL instrumentes et les paquets requis.
    #
    # `.github/**` etait declare volontairement absent au motif que « la CI
    # orchestre la mesure, elle ne la determine pas ». La declaration etait
    # fausse : le job portait les concurrences, la graine et la liste des
    # tests PostgreSQL. Le plan ayant repris ces parametres, elle devient
    # vraie — et les validateurs refusent une campagne qui s'ecarterait du
    # plan, faute de quoi elle resterait une intention.
    "coverage": (
        "app/**/*",
        "tests/**/*",
        "pyproject.toml",
        "requirements.txt",
        "requirements-g0-quality.txt",
        "scripts/g0_coverage_summary.py",
        "scripts/g0_quality_plan.json",
    ),
    # La performance depend du scenario, de l'application mesuree, du schema
    # qu'elle interroge, de l'image construite et de la stack qui l'heberge.
    # `scripts/g0_perf_baseline.py` EN FAIT PARTIE : modifier le scenario doit
    # changer l'empreinte, sans quoi une baseline pourrait decrire un parcours
    # qui n'est plus celui qu'on execute. La surcharge de mesure y figure pour
    # la meme raison : elle desactive les limiteurs de debit, et une baseline
    # qui la modifierait sans changer d'empreinte decrirait un autre systeme.
    # Le plan de mesure aussi : concurrences, repetitions, warm-up, graine,
    # intervalle d'echantillonnage des ressources.
    "performance": (
        "scripts/g0_perf_baseline.py",
        "scripts/g0_perf_overlay.yml",
        "scripts/g0_quality_plan.json",
        "app/**/*",
        "alembic/**/*",
        "docker-compose.yml",
        "Dockerfile",
        "requirements.txt",
    ),
}

#: Répertoires produits par une exécution ou par un gestionnaire de paquets,
#: jamais par un auteur. Les inclure ferait varier l'empreinte selon qu'un test
#: a tourné ou non sur la machine.
#:
#: `artifacts` n'y figure pas : l'ensemble `security` nomme explicitement trois
#: artefacts du lot A, et les exclure en bloc les lui retirerait.
_EXCLUS = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    ".tox",
    "htmlcov",
)

#: Fichiers produits par une exécution : mesures, rapports bruts, bases
#: jetables, journaux. Ils sont écartés **par nom**, quel que soit l'ensemble,
#: parce qu'un motif d'entrée ne peut pas prévoir où une campagne les dépose.
#: Une empreinte qui les absorberait changerait selon qu'une mesure a tourné,
#: le contrôle échouerait toujours, et on finirait par l'ignorer.
_NOMS_EXCLUS = (
    ".coverage",
    ".coverage.*",
    "coverage.xml",
    "coverage.json",
    "coverage-summary.json",
    "perf-baseline.json",
    "perf-provenance.json",
    "*.pyc",
    "*.pyo",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.log",
)


def chemin_relatif(chemin: Path) -> str:
    """Le chemin d'un fichier tel qu'il entre dans l'empreinte."""
    return chemin.relative_to(RACINE).as_posix()


def est_produit_d_execution(nom: str) -> bool:
    """Ce nom de fichier désigne-t-il un produit d'exécution ?

    Écarté **par nom** et non par emplacement : un motif d'entrée ne peut pas
    prévoir où une campagne dépose ses mesures, et `scripts/**/*.json` finirait
    par absorber un rapport brut déposé à côté du script qui l'a produit.
    """
    return any(fnmatch.fnmatch(nom, motif) for motif in _NOMS_EXCLUS)


def fichiers_entree(ensemble: str) -> list[Path]:
    """Les fichiers d'un ensemble d'entrée, triés, sans les produits de build.

    Le tri porte sur la **chaîne POSIX** du chemin, jamais sur l'objet `Path`.
    Comparer deux `Path` emploie la casse repliée sous Windows et la casse
    exacte sous Linux : `Dockerfile` passe avant `alembic/env.py` sur l'un et
    après sur l'autre. Comme l'ordre entre dans l'empreinte, la même
    arborescence produisait deux valeurs selon la machine — la CI Linux a
    refusé une baseline générée sous Windows, à contenu pourtant identique.
    """
    if ensemble not in ENSEMBLES_ENTREE:
        raise KeyError(f"ensemble d'entrée inconnu : {ensemble}")
    trouves: set[Path] = set()
    for motif in ENSEMBLES_ENTREE[ensemble]:
        for chemin in RACINE.glob(motif):
            if not chemin.is_file():
                continue
            parties = chemin.relative_to(RACINE).parts
            if any(exclu in parties for exclu in _EXCLUS):
                continue
            if est_produit_d_execution(chemin.name):
                continue
            trouves.add(chemin)
    return sorted(trouves, key=chemin_relatif)


def _empreinte_fichier(chemin: Path) -> str:
    """Le contenu d'un fichier, insensible à la convention de fin de ligne.

    Un dépôt cloné sous Windows reçoit des CRLF là où Linux reçoit des LF. Sans
    normalisation, la même arborescence donnerait deux empreintes selon la
    machine, et le contrôle en CI échouerait sur une différence qui ne concerne
    pas le contenu.
    """
    octets = chemin.read_bytes()
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(octets).hexdigest()
    return hashlib.sha256(
        texte.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    ).hexdigest()


def empreinte_entrees(ensemble: str) -> tuple[str, int]:
    """Empreinte SHA-256 des entrées réellement lues, et leur nombre.

    Le chemin entre dans l'empreinte au même titre que le contenu : deux
    fichiers échangés produiraient sinon la même valeur.
    """
    accumulateur = hashlib.sha256()
    fichiers = fichiers_entree(ensemble)
    for chemin in fichiers:
        accumulateur.update(chemin_relatif(chemin).encode("utf-8"))
        accumulateur.update(b"\0")
        accumulateur.update(_empreinte_fichier(chemin).encode("ascii"))
        accumulateur.update(b"\0")
    return accumulateur.hexdigest(), len(fichiers)


def _evenement_github() -> dict[str, Any]:
    """Le corps de l'événement GitHub, ou `{}` hors CI. Aucun appel réseau."""
    chemin = os.environ.get("GITHUB_EVENT_PATH")
    if not chemin:
        return {}
    try:
        charge = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return charge if isinstance(charge, dict) else {}


def _arbre_courant() -> str | None:
    """Le SHA de l'arbre de `HEAD`, lu par git. `None` si git ne répond pas."""
    binaire = shutil.which("git")
    if binaire is None:
        return None
    try:
        acheve = subprocess.run(  # noqa: S603 - arguments litteraux, jamais de shell
            [binaire, "-C", str(RACINE), "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return acheve.stdout.strip() or None if acheve.returncode == 0 else None


def identite_de_mesure(job: str) -> dict[str, Any]:
    """Ce que l'artefact doit porter pour se suffire à lui-même.

    Un artefact de mesure qui ne dit pas SUR QUOI il a porté oblige son lecteur
    à retrouver un fichier annexe, ou à faire confiance. `perf-provenance.json`
    portait bien `baseline_input_commit`, mais ce champ est l'**ancrage
    historique du programme G0** — un point de départ déclaré, permanent —
    et non le commit mesuré. Lu seul, il induisait en erreur.

    Les six identités sont donc embarquées dans l'artefact lui-même. Elles sont
    distinctes, et les confondre a des conséquences : sur un événement
    `pull_request`, ``GITHUB_SHA`` désigne le commit de fusion **synthétique**
    que GitHub fabrique pour l'occasion, pas la tête de la branche. Une campagne
    qui citerait ce SHA renverrait à un commit qui n'existe sur aucune
    référence.

    ``workflow_job_id`` — l'identifiant NUMÉRIQUE d'un job n'est exposé par
    aucune variable d'environnement du runner : l'obtenir exige un appel à
    l'API, donc le droit ``actions: read`` sur un workflow qui n'a aujourd'hui
    que ``contents: read``, et une campagne qui échouerait sur un incident
    d'API. Il est donc renseigné **lorsque le workflow le fournit**
    (``G0_WORKFLOW_JOB_ID``), et l'identification repose sinon sur le triplet
    ``workflow_run_id`` + ``workflow_run_attempt`` + ``workflow_job``, qui
    désigne le job sans ambiguïté et se résout en identifiant numérique pour
    quiconque a accès au dépôt. Le choix est écrit ici plutôt que laissé à
    deviner devant un champ vide.
    """
    evenement = _evenement_github()
    pr = evenement.get("pull_request") or {}
    tete_pr = str((pr.get("head") or {}).get("sha") or "")
    base = str((pr.get("base") or {}).get("sha") or "")
    github_sha = os.environ.get("GITHUB_SHA", "")

    if tete_pr:
        # Evenement `pull_request` : GITHUB_SHA est la fusion synthetique.
        source, fusion = tete_pr, github_sha
    else:
        # `push` ou `workflow_dispatch` : GITHUB_SHA EST la tete, et il
        # n'existe aucune fusion synthetique a enregistrer.
        source, fusion = github_sha, ""

    return {
        "_comment": (
            "Identites de la mesure, embarquees pour que cet artefact se suffise "
            "a lui-meme. Ne pas confondre avec baseline_input_commit, qui est "
            "l'ancrage historique DECLARE du programme G0 et non le commit mesure."
        ),
        "measurement_source_sha": source or None,
        "base_sha": base or None,
        "tested_merge_sha": fusion or None,
        "tested_tree_sha": _arbre_courant(),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID") or None,
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT") or None,
        "workflow_job": os.environ.get("GITHUB_JOB") or job,
        "workflow_job_id": os.environ.get("G0_WORKFLOW_JOB_ID") or None,
        "event_name": os.environ.get("GITHUB_EVENT_NAME") or None,
    }


def ecarts_identite(embarquee: Any, sidecar: Any) -> list[str]:
    """Compare l'identité embarquée à celle du fichier voisin écrit par la CI.

    Deux écritures indépendantes de la même vérité : l'une par le générateur en
    Python, l'autre par le job en shell. Si elles divergent, l'une des deux ment
    — et rien, dans un artefact isolé, ne permettrait de savoir laquelle.
    """
    ecarts: list[str] = []
    if not isinstance(embarquee, dict):
        return ["identite de mesure absente de l'artefact"]
    for cle in ("measurement_source_sha", "workflow_run_id", "workflow_job"):
        if not embarquee.get(cle):
            ecarts.append(f"identite de mesure incomplete : {cle} absent")
    source = str(embarquee.get("measurement_source_sha") or "")
    fusion = str(embarquee.get("tested_merge_sha") or "")
    if source and fusion and source == fusion:
        ecarts.append(
            "measurement_source_sha = tested_merge_sha : la tete de la branche a "
            "ete confondue avec le commit de fusion synthetique de GitHub"
        )
    if not isinstance(sidecar, dict):
        return ecarts
    for cle in ("measurement_source_sha", "base_sha", "tested_tree_sha", "workflow_run_id"):
        attendue, obtenue = sidecar.get(cle), embarquee.get(cle)
        if attendue in (None, "") or obtenue in (None, ""):
            continue
        if str(attendue) != str(obtenue):
            ecarts.append(
                f"identite incoherente sur {cle} : artefact {obtenue!r}, "
                f"fichier de la CI {attendue!r}"
            )
    return ecarts


def provenance(
    ensemble: str,
    commande: str,
    *,
    schema_version: str,
    generator_version: str,
) -> dict[str, Any]:
    """La provenance d'un artefact, séparée en ce qui se compare et ce qui varie.

    `deterministic` est comparé par `--check` : une entrée modifiée doit obliger
    à régénérer. `volatile` ne l'est pas — inclure l'heure produirait un diff à
    chaque exécution, le contrôle échouerait toujours, on finirait par
    l'ignorer.
    """
    empreinte, nombre = empreinte_entrees(ensemble)
    return {
        "_comment": (
            "deterministic est compare par --check ; volatile ne l'est pas. "
            "baseline_input_commit est l'ANCRAGE HISTORIQUE DECLARE du programme "
            "G0 (reference permanente) : ce N'EST PAS le commit mesure, et le "
            "lire comme tel induit en erreur. Le commit reellement mesure figure "
            "dans measurement_identity, pour les artefacts qui en portent une. "
            "relevant_input_tree_sha256 est la preuve verifiable : l'empreinte "
            "des octets reellement lus."
        ),
        "deterministic": {
            "schema_version": schema_version,
            "generator_version": generator_version,
            "generation_command": commande,
            "baseline_input_commit": BASELINE_INPUT_COMMIT,
            "baseline_input_ref": BASELINE_INPUT_REF,
            "relevant_input_set": ensemble,
            "relevant_input_patterns": list(ENSEMBLES_ENTREE[ensemble]),
            "relevant_input_file_count": nombre,
            "relevant_input_tree_sha256": empreinte,
        },
        "volatile": {
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "platform": f"{platform.system().lower()}/{platform.machine().lower()}",
            "python_version": platform.python_version(),
        },
    }


def controler(chemin: Path, attendue: dict[str, Any]) -> list[str]:
    """Compare la partie déterministe d'une provenance versionnée.

    Renvoie la liste des écarts, vide si tout concorde. La partie `volatile`
    est ignorée : la comparer ferait échouer le contrôle à chaque exécution.
    """
    if not chemin.is_file():
        return [f"{chemin.name} absent"]
    versionnee = json.loads(chemin.read_text(encoding="utf-8")).get("deterministic")
    if versionnee is None:
        return [f"{chemin.name} : bloc `deterministic` absent — provenance obsolète"]
    ecarts = []
    for cle, valeur in attendue["deterministic"].items():
        if versionnee.get(cle) != valeur:
            ecarts.append(f"{chemin.name} : {cle} = {versionnee.get(cle)!r}, attendu {valeur!r}")
    return ecarts

"""L'identité de mesure d'une campagne G0 — sur quoi elle a réellement porté.

POURQUOI CE MODULE EXISTE À PART
--------------------------------
Ce code a d'abord été écrit dans `g0_provenance.py`. C'était une erreur, et la
CI du lot A l'a dite sans détour : ce module porte dans sa propre docstring le
contrat « aucun sous-processus, aucun appel réseau », et son job de CI exige
**zéro** alerte Bandit. Y ajouter un appel à `git` violait les deux.

Le contrat n'était pas décoratif. `g0_provenance.py` est lu par les générateurs
des lots A, B et C ; lui donner le droit de lancer des sous-processus l'aurait
ouvert à tous, pour le besoin d'un seul.

L'identité de mesure est un besoin du **lot C** : elle décrit une campagne
exécutée en CI. Elle vit donc ici, avec ses deux alertes Bandit assumées et
argumentées (import de `subprocess`, appel à arguments littéraux sans shell),
et le lot A garde son zéro.

CE QUE CE MODULE RÉSOUT
-----------------------
`perf-provenance.json` portait `baseline_input_commit`, qui est l'**ancrage
historique déclaré** du programme G0 — pas le commit mesuré. Lu seul,
l'artefact induisait en erreur. Les identités sont désormais embarquées dans
les artefacts eux-mêmes : un lecteur du seul fichier canonique sait sur quelle
tête la mesure a porté.

Aucun secret, aucune donnée patient.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[1]


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

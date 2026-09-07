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

import hashlib
import platform
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
    # L'inventaire lit le code, les migrations, les fichiers d'orchestration et
    # la définition de la CI.
    "inventory": (
        "app/**/*",
        "alembic/**/*",
        "deploy/**/*",
        "monitoring/**/*",
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
}

#: Répertoires et fichiers produits par l'exécution, jamais par un auteur.
#: Les inclure ferait varier l'empreinte selon qu'un test a tourné ou non.
_EXCLUS = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")


def chemin_relatif(chemin: Path) -> str:
    """Le chemin d'un fichier tel qu'il entre dans l'empreinte."""
    return chemin.relative_to(RACINE).as_posix()


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
            if chemin.suffix in (".pyc", ".pyo"):
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
            "baseline_input_commit est DECLARE (reference permanente), jamais "
            "derive de la branche de travail. relevant_input_tree_sha256 est la "
            "preuve verifiable : l'empreinte des octets reellement lus."
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
    import json

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

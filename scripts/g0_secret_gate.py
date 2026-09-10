"""Barrière de secrets G0 — bloquante, sur l'arbre courant et sur l'historique.

Pourquoi ce script existe alors que `detect-secrets` a déjà une commande.

1. **La commande seule ne peut pas bloquer aujourd'hui.** `.secrets.baseline`
   couvre 14 fichiers ; l'arbre en compte 88 qui déclenchent une règle. Le
   contrôle était donc `continue-on-error: true` — c'est-à-dire décoratif.
   Le rendre bloquant sans registre d'exceptions aurait rendu la CI rouge en
   permanence, ce qui revient au même : un contrôle qu'on ignore.

2. **Les chemins de `.secrets.baseline` sont écrits à la mode Windows.** Treize
   de ses quatorze clés portent des séparateurs `\\`. Sur un runner Linux,
   `detect-secrets` produit `tests/conftest.py` et ne retrouve jamais
   `tests\\conftest.py` : *aucune* entrée de la baseline ne s'applique en CI.
   Ce script normalise les séparateurs **à la lecture**. Il ne réécrit pas le
   fichier : le lot B photographie, il ne corrige pas. Le défaut est enregistré
   comme constat, et la compensation appliquée ici en est la preuve.

3. **L'historique n'était pas scanné du tout.** Un secret retiré de l'arbre
   reste lisible dans l'objet Git qui le contenait. Gitleaks parcourt les
   commits ; ce script consomme son rapport et applique le même registre.

**Aucune valeur n'est jamais affichée ni écrite**, pas même tronquée. Seuls
circulent le chemin, la règle déclenchée, l'empreinte — SHA-1 calculé par
`detect-secrets`, ou le champ `Fingerprint` que Gitleaks compose lui-même — et
le jugement enregistré. Un fragment de secret reste un indice.

**Le registre d'exceptions ne se remplit pas tout seul.** `--propose` écrit une
proposition à partir de familles de chemins *écrites à la main* dans
`FAMILLES_REVUES` ; un chemin qui n'appartient à aucune famille revue sort en
`NON_REVU`, et la barrière le refuse. Accepter automatiquement tout ce qui est
trouvé aurait produit un registre qui dit oui à tout.

Aucun sous-processus : les rapports Gitleaks et les comptages de commits sont
produits par le workflow, et seulement lus ici. Ce script juge, il ne mesure pas
l'état de Git — ce partage garde une barrière de sécurité exempte de tout appel
de processus. Aucun appel réseau. Aucune donnée patient.
"""

from __future__ import annotations

import argparse
import base64
import builtins
import contextlib
import fnmatch
import json
import re
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[1]
BASELINE = RACINE / ".secrets.baseline"
REGISTRE = RACINE / "docs" / "governance" / "SECRET_SCAN_EXCEPTIONS.json"

#: Sentinelle des sondes de non-vacuité, **assemblée à l'exécution**.
#:
#: Écrite en un seul littéral, elle aurait la forme d'une clé d'accès AWS et
#: serait détectée dans ce fichier même : le dépôt principal porterait alors
#: une valeur ressemblant à un secret actif, ce que la campagne s'interdit.
#: Assemblée, elle n'existe qu'en mémoire, et les deux scanners la voient
#: apparaître dans le dépôt jetable de la sonde.
SENTINELLE_SONDE = "AK" + "IA" + "Q7XKJ92MW" + "VD3B5N4"

#: Seconde forme de sentinelle : en-tête de clé privée PEM, elle aussi
#: assemblée à l'exécution.
#:
#: Une sonde à UNE seule forme ne teste que la règle qui la reconnaît. La
#: première version portait les mots PROBE et SENTINEL : la liste de mots
#: vides de Gitleaks les écarte, et la sonde positive est sortie en
#: POSITIVE_PROBE_MISSED alors que le scanner fonctionnait. Mesuré en CI, pas
#: supposé — et corrigé en retirant tout mot du dictionnaire de la valeur, et
#: en ajoutant une seconde forme qu'aucune liste de mots ne peut écarter.
SENTINELLE_PEM_DEBUT = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
SENTINELLE_PEM_FIN = "-----END " + "RSA PRIVATE KEY" + "-----"


def contenu_porteur() -> str:
    """Le fichier que les deux scanners DOIVENT relever.

    Deux formes, et un bloc PEM **complet**. La première rédaction ne portait
    que la ligne `BEGIN` : la règle `private-key` de Gitleaks exige le bloc
    entier, ligne `END` comprise, et la sonde sortait donc en
    POSITIVE_PROBE_MISSED — mesuré en CI, deux fois.

    Le corps du bloc n'est pas une clé : c'est l'encodage base64 d'une phrase
    française qui le dit. Aucune valeur ressemblant à un secret actif n'entre
    dans le dépôt : tout est assemblé à l'exécution.
    """
    corps = base64.b64encode(
        ("Ceci n'est pas une cle. Sentinelle de non-vacuite du lot B du gate G0. " * 2).encode()
    ).decode()
    saut = chr(10)
    return saut.join(
        (
            f"aws_access_key_id = {SENTINELLE_SONDE}",
            SENTINELLE_PEM_DEBUT,
            corps[:64],
            corps[64:128],
            SENTINELLE_PEM_FIN,
            "",
        )
    )


#: Contenu du fichier propre de la sonde négative. Aucune règle ne s'y applique.
TEXTE_PROPRE = "Ce fichier ne contient aucune valeur sensible.\nligne de texte ordinaire\n"

#: Répertoires jamais scannés : produits d'exécution, dépendances, métadonnées
#: Git. Les inclure ferait dépendre le résultat de ce qui a tourné avant.
REPERTOIRES_EXCLUS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
)

#: Suffixes binaires : les scanner produit du bruit, jamais une preuve.
SUFFIXES_EXCLUS = frozenset({".ico", ".jpeg", ".jpg", ".pdf", ".png", ".pyc", ".pyo", ".woff2"})

#: Les deux registres eux-mêmes, exclus du scan.
#:
#: Ils ne contiennent aucune valeur — seulement des empreintes SHA-1 et SHA-256.
#: Les scanner ferait relever ces empreintes comme des chaînes hexadécimales à
#: forte entropie, qu'il faudrait à leur tour inscrire dans le registre, dont les
#: nouvelles empreintes seraient relevées à la génération suivante : le fichier
#: grossirait sans fin sans jamais rien prouver. `detect-secrets` applique
#: exactement la même exclusion à sa propre baseline, par le filtre
#: `is_baseline_file`.
FICHIERS_EXCLUS = frozenset({".secrets.baseline", "docs/governance/SECRET_SCAN_EXCEPTIONS.json"})

#: Les fichiers de provenance G0, exclus pour la MEME raison, et vérifiée.
#:
#: Ils ne contiennent qu'une chose sensible à l'entropie : `relevant_input_tree_sha256`,
#: l'empreinte SHA-256 des fichiers d'entrée. `detect-secrets` la relève comme une
#: chaîne hexadécimale à forte entropie — ce qu'elle est, sans être un secret.
#:
#: Les inscrire au registre ne tient pas : la clé d'acceptation est le hachage de la
#: VALEUR, et cette valeur change à chaque régénération, c'est-à-dire dès qu'un fichier
#: d'entrée change. Six entrées du registre étaient dans ce cas, et il aurait fallu les
#: réécrire à chaque passage. Un registre qu'on réécrit machinalement est un registre
#: qu'on ne relit plus — le défaut que cette barrière combat par ailleurs.
#:
#: L'exclusion est donc structurelle, et compensée : ces fichiers passent par le
#: validateur spécialisé, au même titre que la baseline et le registre.
MOTIFS_FICHIERS_EXCLUS = ("artifacts/g0/*provenance*.json",)


# ── Familles revues ─────────────────────────────────────────────────────────
#
# La seule décision humaine du dispositif. Chaque famille dit ce que sont les
# valeurs trouvées à cet endroit, et pourquoi les accepter ne crée pas de
# risque. Un chemin hors de ces familles n'est pas accepté : il ressort en
# `NON_REVU` et fait échouer la barrière.

FAMILLES_REVUES: tuple[dict[str, Any], ...] = (
    {
        "id": "tests",
        "motifs": ("tests/*", "tests/**/*"),
        "caractere": "FACTICE_DE_TEST",
        "rotation_necessaire": False,
        "justification": (
            "Identifiants littéraux de comptes créés puis détruits par le test lui-même, "
            "sur une base SQLite jetable. Ils ne désignent aucun système, ne survivent pas "
            "à la session de test, et plusieurs tests portent précisément sur le refus de "
            "mots de passe faibles — les écrire est la condition du test."
        ),
    },
    {
        "id": "scripts_utilitaires",
        "motifs": (
            "scripts/check_pw.py",
            "scripts/verify_db_password.py",
            "scripts/uat_smoke.py",
        ),
        "caractere": "FACTICE_DE_TEST",
        "rotation_necessaire": False,
        "justification": (
            "Utilitaires locaux de vérification et parcours de recette. Les valeurs sont "
            "des mots de passe d'essai créés dans l'environnement de test au moment de "
            "l'exécution ; aucun ne désigne un compte durable."
        ),
    },
    {
        "id": "empreintes_publiques",
        "motifs": (
            "artifacts/g0/*.json",
            "scripts/g0_provenance.py",
            "scripts/g0_secret_gate.py",
        ),
        "caractere": "EMPREINTE_PUBLIQUE",
        "rotation_necessaire": False,
        "justification": (
            "Empreintes SHA-256 d'arbres d'entrée et SHA de commits Git. Une empreinte "
            "est publiée pour être comparée : elle n'ouvre aucun accès et n'a rien à "
            "protéger. Le détecteur d'entropie hexadécimale les relève par construction."
        ),
    },
    {
        "id": "generateurs_g0",
        "motifs": ("scripts/g0_*.py",),
        "caractere": "LIBELLE_DE_CLASSIFICATION",
        "rotation_necessaire": False,
        "justification": (
            "Les générateurs de la baseline nomment des catégories et des réglages qui "
            "contiennent les mots « secret » ou « key » — par exemple la catégorie "
            "AUTHENTIFICATION_SECRET, dont la valeur est un niveau de risque. Le "
            "détecteur de mots-clés relève l'affectation ; ce sont des libellés de "
            "classification, jamais des valeurs."
        ),
    },
    {
        # Placee AVANT `documentation` : la premiere famille qui correspond
        # gagne, et ranger cette cle sous « exemple documentaire » serait faux.
        "id": "cle_publiable_projet_reel",
        "motifs": (".env.example",),
        "caractere": "CLE_PUBLIABLE_DE_PROJET_REEL",
        "rotation_necessaire": True,
        "justification": (
            "Historique de `.env.example` : cle `sb_publishable_*` d'un projet Supabase de "
            "PREPRODUCTION reel, et son URL. Supabase designe ce prefixe comme publiable — "
            "la cle est livree dans les bundles navigateur et la protection repose sur RLS, "
            "ce n'est donc pas un secret au sens cryptographique. Elle identifie neanmoins "
            "un projet reel, et l'arbre courant porte desormais des marque-places : la "
            "valeur ne subsiste que dans l'historique. Rotation a decider par le "
            "proprietaire — voir le constat B-13."
        ),
    },
    {
        "id": "documentation",
        "motifs": (
            ".env.example",
            "docs/*.md",
            "docs/**/*.md",
            "docs/**/*.json",
        ),
        "caractere": "EXEMPLE_DOCUMENTAIRE",
        "rotation_necessaire": False,
        "justification": (
            "Marque-place et valeurs d'illustration destinés à être remplacés au "
            "déploiement, ou identifiants de conteneurs jetables cités dans une "
            "procédure reproductible. Aucun n'est utilisé par le système."
        ),
    },
    {
        "id": "ci_jetable",
        "motifs": (".github/workflows/*.yml",),
        "caractere": "SECRET_DE_CI_NON_PRODUCTION",
        "rotation_necessaire": False,
        "justification": (
            "Identifiants de bases et de comptes créés puis détruits dans le runner, "
            "écrits en clair pour que le pipeline soit rejouable. Ils ne désignent aucun "
            "système durable et ne survivent pas au job."
        ),
    },
)


def famille_de(chemin: str) -> dict[str, Any] | None:
    """La famille revue qui couvre ce chemin, ou `None` s'il n'en a pas."""
    for famille in FAMILLES_REVUES:
        if any(fnmatch.fnmatch(chemin, motif) for motif in famille["motifs"]):
            return famille
    return None


# ── Lecture de `.secrets.baseline` ──────────────────────────────────────────


def charger_baseline() -> tuple[set[tuple[str, str, str]], list[str]]:
    """Les entrées de la baseline, et les chemins qu'il a fallu normaliser.

    La normalisation est faite **ici**, à la lecture. Le fichier versionné n'est
    pas modifié : son défaut appartient au constat, pas à la remédiation.
    """
    if not BASELINE.is_file():
        raise SystemExit(f"baseline de secrets absente : {BASELINE}")
    contenu = json.loads(BASELINE.read_text(encoding="utf-8"))
    connues: set[tuple[str, str, str]] = set()
    non_posix: list[str] = []
    for fichier, occurrences in contenu.get("results", {}).items():
        normalise = fichier.replace("\\", "/")
        if normalise != fichier:
            non_posix.append(normalise)
        for occurrence in occurrences:
            connues.add((normalise, occurrence["type"], occurrence["hashed_secret"]))
    return connues, sorted(non_posix)


def configuration_scan() -> dict[str, Any]:
    """Les règles et filtres du dépôt, repris tels quels de `.secrets.baseline`.

    Redéfinir ici une liste de plugins ferait diverger la barrière du crochet de
    pré-commit : deux outils qui disent des choses différentes ne prouvent rien.
    """
    contenu = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {
        "plugins_used": contenu["plugins_used"],
        "filters_used": contenu["filters_used"],
    }


# ── Inventaire des fichiers ─────────────────────────────────────────────────


def exclu_du_scan(chemin: str) -> bool:
    """La meme politique d'exclusion pour les deux scanners.

    `detect-secrets` recoit une liste de chemins deja filtree ; Gitleaks, lui,
    parcourt le repertoire et l'historique tout seul. Sans ce filtre applique a
    son rapport, les deux outils ne parleraient pas du meme perimetre, et le
    registre devrait couvrir des fichiers que l'autre n'a jamais lus.
    """
    if chemin in FICHIERS_EXCLUS:
        return True
    if any(fnmatch.fnmatch(chemin, motif) for motif in MOTIFS_FICHIERS_EXCLUS):
        return True
    if Path(chemin).suffix.lower() in SUFFIXES_EXCLUS:
        return True
    return any(partie in REPERTOIRES_EXCLUS for partie in Path(chemin).parts)


def fichiers_a_scanner(liste: Path | None) -> list[str]:
    """Les chemins à scanner, triés sur la **chaîne POSIX**.

    Trier des objets `Path` replierait la casse sous Windows et pas sous Linux :
    l'ordre du rapport dépendrait de la machine.
    """
    if liste is not None:
        chemins = [
            ligne.strip().replace("\\", "/")
            for ligne in liste.read_text(encoding="utf-8").splitlines()
            if ligne.strip()
        ]
    else:
        chemins = []
        for chemin in RACINE.rglob("*"):
            if not chemin.is_file():
                continue
            parties = chemin.relative_to(RACINE).parts
            if any(partie in REPERTOIRES_EXCLUS for partie in parties):
                continue
            chemins.append(chemin.relative_to(RACINE).as_posix())
    # `exclu_du_scan` est la SEULE politique d'exclusion. La dupliquer ici a
    # failli laisser passer un ecart : les motifs de fichiers exclus ne
    # s'appliquaient qu'au rapport Gitleaks, pas a la liste donnee a
    # detect-secrets, et les deux outils n'auraient plus parle du meme perimetre.
    retenus = [c for c in chemins if not exclu_du_scan(c)]
    return sorted(set(retenus))


# ── Scan de l'arbre courant ─────────────────────────────────────────────────


@contextlib.contextmanager
def lecture_en_utf8() -> Iterator[None]:
    """Force `open()` à lire en UTF-8 le temps du scan.

    `detect-secrets` ouvre les fichiers avec `open(chemin)`, donc avec l'encodage
    de la locale. Sous Linux c'est UTF-8 ; sous Windows c'est `cp1252`, et un
    fichier UTF-8 contenant un octet invalide dans cette table y provoque une
    `UnicodeDecodeError` que l'outil **avale silencieusement** : le fichier n'est
    pas scanné, et rien ne le signale.

    Le symptôme a été mesuré : `tests/test_qc.py` porte une affectation de mot de
    passe littérale que la CI Linux relève et que la même commande, sur le même
    fichier, ne relevait pas sous Windows. Un registre d'exceptions construit
    sous Windows sous-comptait donc, et la CI le refusait — à juste titre.

    Sans ce forçage, la mesure dépendrait de la machine qui la produit, ce qui la
    priverait de toute valeur de preuve.
    """
    original = builtins.open

    def ouvrir(fichier: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if "b" not in mode and not args and kwargs.get("encoding") is None:
            kwargs["encoding"] = "utf-8"
        return original(fichier, mode, *args, **kwargs)

    builtins.open = ouvrir  # type: ignore[assignment]
    try:
        yield
    finally:
        builtins.open = original  # type: ignore[assignment]


def scanner_arbre(
    chemins: list[str], racine: Path | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Les détections `detect-secrets` de l'arbre, et le compte rendu du scan.

    `secret_hash` est le SHA-1 que `detect-secrets` calcule sur la valeur : il
    identifie une occurrence sans la révéler, et c'est lui qui sert de clé au
    registre d'exceptions.

    **Aucune erreur de lecture n'est avalée.** La version précédente faisait
    `except (OSError, UnicodeDecodeError): continue` : un fichier illisible, une
    permission refusée, un fichier disparu entre l'inventaire et la lecture, ou
    une exception interne du scanner produisaient exactement le même résultat
    qu'un fichier propre — zéro détection. Une barrière qui confond « rien
    trouvé » et « pas regardé » ne prouve rien, et c'est précisément dans les
    fichiers qu'on n'arrive pas à lire qu'un secret aurait le plus de chances de
    survivre.

    Chaque fichier de la liste tombe donc dans exactement une catégorie —
    `SCANNED` ou `EXPLICITLY_EXCLUDED` — et tout autre cas alimente
    `scan_errors`, ce qui rend la barrière rouge sous le code
    `SECRET_SCAN_INCOMPLETE`.
    """
    from detect_secrets.core import scan
    from detect_secrets.settings import transient_settings

    base = racine or RACINE
    trouvees: list[dict[str, Any]] = []
    scannes: list[str] = []
    exclus: list[str] = []
    erreurs: list[dict[str, str]] = []

    with transient_settings(configuration_scan()), lecture_en_utf8():
        for chemin in chemins:
            if exclu_du_scan(chemin):
                exclus.append(chemin)
                continue
            absolu = base / chemin
            try:
                if not absolu.is_file():
                    erreurs.append({"path": chemin, "reason": "FILE_MISSING_AT_READ_TIME"})
                    continue
                detections = list(scan.scan_file(str(absolu)))
            except UnicodeDecodeError:
                erreurs.append({"path": chemin, "reason": "DECODE_ERROR"})
                continue
            except PermissionError:
                erreurs.append({"path": chemin, "reason": "PERMISSION_DENIED"})
                continue
            except OSError as erreur:
                erreurs.append({"path": chemin, "reason": f"OS_ERROR:{type(erreur).__name__}"})
                continue
            except Exception as erreur:  # noqa: BLE001 — un scanner qui plante est un trou de mesure
                erreurs.append({"path": chemin, "reason": f"SCANNER_ERROR:{type(erreur).__name__}"})
                continue
            scannes.append(chemin)
            for detection in detections:
                trouvees.append(
                    {
                        "scanner": "detect-secrets",
                        "path": chemin,
                        "rule": detection.type,
                        "fingerprint": detection.secret_hash,
                        "scope": "tree",
                    }
                )

    rapport = {
        "attempted_files": len(chemins),
        "successfully_scanned_files": len(scannes),
        "explicitly_excluded_files": len(exclus),
        "scan_errors": sorted(erreurs, key=lambda e: e["path"]),
        "complete": not erreurs and len(scannes) + len(exclus) == len(chemins),
    }
    return sorted(trouvees, key=lambda t: (t["path"], t["rule"], t["fingerprint"])), rapport


# ── Lecture des rapports Gitleaks ───────────────────────────────────────────


class DetectionSansEmpreinte(RuntimeError):
    """Un finding Gitleaks sans `Fingerprint` — la barrière ne peut pas l'identifier.

    Se rabattre sur autre chose reviendrait à accepter une détection qu'on ne
    sait pas nommer. Le code d'incident est `GITLEAKS_FINDING_WITHOUT_FINGERPRINT`.
    """


def lire_rapport_gitleaks(chemin: Path, portee: str) -> list[dict[str, Any]]:
    """Les détections d'un rapport Gitleaks JSON, réduites à ce qui ne fuit pas.

    **L'identité d'une détection Gitleaks est son champ `Fingerprint`**, et rien
    d'autre. Gitleaks le compose lui-même — `commit:fichier:règle:ligne` pour un
    scan d'historique, `fichier:règle:ligne` pour un scan d'arbre — de sorte que
    deux valeurs différentes au même endroit portent deux identités différentes.

    La première version de ce lecteur inscrivait le SHA du **commit** dans le
    champ `fingerprint`, ou la chaîne `arbre-courant` à défaut. Ce n'était pas
    une identité : deux secrets distincts introduits par le même commit
    recevaient la même. Combiné à une clé d'acceptation qui ignorait ce champ,
    l'effet était qu'un chemin déjà qualifié absorbait silencieusement toute
    nouvelle détection portant la même règle.

    Gitleaks est appelé avec `--redact` : `Secret` et `Match` sont déjà remplacés
    côté outil. Ce lecteur ne les recopie pas pour autant — ils ne franchissent
    jamais cette frontière.
    """
    if not chemin.is_file():
        raise SystemExit(f"rapport Gitleaks absent : {chemin}")
    texte = chemin.read_text(encoding="utf-8").strip()
    brut = json.loads(texte) if texte else []
    detections: list[dict[str, Any]] = []
    sans_empreinte: list[str] = []
    for element in brut:
        fichier = str(element.get("File", "")).replace("\\", "/")
        if exclu_du_scan(fichier):
            continue
        empreinte = str(element.get("Fingerprint", "") or "").strip()
        if not empreinte:
            sans_empreinte.append(f"{fichier}[{element.get('RuleID', '')}]")
            continue
        detections.append(
            {
                "scanner": f"gitleaks-{portee}",
                "path": fichier,
                "rule": str(element.get("RuleID", "")),
                "fingerprint": empreinte,
                "commit": str(element.get("Commit", "") or ""),
                "start_line": int(element.get("StartLine", 0) or 0),
                "scope": "history" if portee == "historique" else "tree",
            }
        )
    if sans_empreinte:
        raise DetectionSansEmpreinte(
            "GITLEAKS_FINDING_WITHOUT_FINGERPRINT : "
            f"{len(sans_empreinte)} détection(s) sans champ Fingerprint dans {chemin.name} — "
            f"{', '.join(sorted(set(sans_empreinte))[:5])}"
        )
    return sorted(detections, key=lambda t: (t["path"], t["rule"], t["fingerprint"]))


# ── Registre d'exceptions ───────────────────────────────────────────────────


def charger_registre() -> dict[str, Any]:
    if not REGISTRE.is_file():
        raise SystemExit(
            f"registre d'exceptions absent : {REGISTRE}. "
            "Le produire avec --propose, puis le relire avant de le versionner."
        )
    return json.loads(REGISTRE.read_text(encoding="utf-8"))


def _cle(detection: dict[str, Any]) -> tuple[str, str, str, str]:
    """La clé d'acceptation d'une détection — son identité propre, toujours.

    Pour `detect-secrets`, c'est l'empreinte SHA-1 de la valeur : elle identifie
    l'occurrence exacte sans la révéler.

    Pour Gitleaks, c'est son `Fingerprint`, tel que l'outil l'a écrit.

    La version précédente renvoyait `(scanner, chemin, règle)` pour Gitleaks, en
    justifiant qu'inclure le commit rendrait le registre faux à chaque nouveau
    commit. Le raisonnement partait d'une prémisse fausse — le commit n'est pas
    l'identité d'une détection — et sa conséquence était grave : **une nouvelle
    valeur détectable, ajoutée dans un fichier déjà qualifié sous la même
    règle, passait sans être revue.** La revue l'a démontré par mutation.

    Le chemin, la règle, le commit et la ligne restent inscrits comme
    métadonnées de lecture ; aucun ne remplace l'empreinte. Un registre plus
    long est le prix d'un registre qui dit la vérité.
    """
    empreinte = str(detection.get("fingerprint", "") or "")
    if not empreinte:
        raise DetectionSansEmpreinte(
            "GITLEAKS_FINDING_WITHOUT_FINGERPRINT : détection sans empreinte — "
            f"{detection.get('scanner')} {detection.get('path')}"
        )
    return (detection["scanner"], detection["path"], detection["rule"], empreinte)


def confronter(
    detections: list[dict[str, Any]],
    connues_baseline: set[tuple[str, str, str]],
    registre: dict[str, Any],
) -> dict[str, Any]:
    """Sépare ce qui est couvert par écrit de ce qui ne l'est pas.

    Trois voies d'acceptation, et aucune autre : la baseline versionnée du
    dépôt, le registre d'exceptions relu, et rien d'autre. Un défaut de
    couverture est un échec, pas un avertissement.
    """
    acceptees = {_cle(entree) for entree in registre.get("exceptions", [])}
    couvertes: list[dict[str, Any]] = []
    residus: list[dict[str, Any]] = []
    for detection in detections:
        par_baseline = (
            detection["scanner"] == "detect-secrets"
            and (detection["path"], detection["rule"], detection["fingerprint"]) in connues_baseline
        )
        if par_baseline or _cle(detection) in acceptees:
            couvertes.append(
                {**detection, "source": ".secrets.baseline" if par_baseline else "registre"}
            )
        else:
            residus.append(detection)
    return {"couvertes": couvertes, "residus": residus}


def _commit_documentaire(
    detection: dict[str, Any],
    precedente: dict[str, Any] | None,
    registre_courant: dict[str, Any],
) -> str:
    """Le commit inscrit a titre documentaire, jamais devine.

    Pour une detection d'historique, Gitleaks nomme le commit ou la valeur
    apparait : c'est lui qu'on inscrit. Pour l'arbre courant, il n'y en a pas —
    le commit d'introduction du fichier est renseigne separement, et a defaut
    l'entree porte le commit de revue.
    """
    if precedente and precedente.get("commit"):
        return str(precedente["commit"])
    commit = str(detection.get("commit", "") or "")
    if commit:
        return commit
    return str(registre_courant.get("review_commit", ""))


def proposer(
    detections: list[dict[str, Any]],
    registre_courant: dict[str, Any],
    connues_baseline: set[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Une proposition de registre, à relire avant d'être versionnée.

    La justification vient de la famille de chemins, écrite à la main. Un chemin
    sans famille reçoit `NON_REVU` : la barrière le refusera, et c'est
    volontaire — c'est là qu'un humain doit trancher.

    Ce que `.secrets.baseline` couvre déjà n'est pas repris : deux registres qui
    se recouvrent finiraient par se contredire, et on ne saurait plus lequel
    fait foi.
    """
    deja = connues_baseline or set()
    anciennes = {_cle(e): e for e in registre_courant.get("exceptions", [])}
    exceptions: list[dict[str, Any]] = []
    for detection in detections:
        if (
            detection["scanner"] == "detect-secrets"
            and (detection["path"], detection["rule"], detection["fingerprint"]) in deja
        ):
            continue
        precedente = anciennes.get(_cle(detection))
        famille = famille_de(detection["path"])
        exceptions.append(
            {
                "scanner": detection["scanner"],
                "path": detection["path"],
                "rule": detection["rule"],
                "fingerprint": detection["fingerprint"],
                "start_line": int(detection.get("start_line", 0) or 0),
                "scope": str(detection.get("scope", "tree")),
                "commit": _commit_documentaire(detection, precedente, registre_courant),
                "family": famille["id"] if famille else "NON_REVU",
                "character": famille["caractere"] if famille else "A_QUALIFIER",
                "rotation_required": (not famille) or bool(famille["rotation_necessaire"]),
                "justification": (
                    famille["justification"]
                    if famille
                    else "Aucune famille revue ne couvre ce chemin — à qualifier à la main."
                ),
            }
        )
    # Déduplication sur la CLÉ D'ACCEPTATION, c'est-à-dire sur l'identité propre
    # de la détection. Deux findings de même empreinte sont le même fait rapporté
    # deux fois ; deux empreintes différentes sont deux décisions à prendre, même
    # dans le même fichier et sous la même règle. La version précédente fusionnait
    # ce second cas, et c'est ainsi qu'une nouvelle valeur passait inaperçue.
    uniques: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for exception in exceptions:
        cle = _cle(exception)
        if cle in uniques:
            uniques[cle]["occurrences"] = uniques[cle].get("occurrences", 1) + 1
            continue
        uniques[cle] = exception
    exceptions = sorted(
        uniques.values(), key=lambda e: (e["scanner"], e["path"], e["rule"], e["fingerprint"])
    )
    return {
        "_comment": registre_courant.get("_comment", ""),
        "review_commit": registre_courant.get("review_commit", ""),
        "families": [
            {
                "id": f["id"],
                "path_patterns": list(f["motifs"]),
                "character": f["caractere"],
                "rotation_required": f["rotation_necessaire"],
                "justification": f["justification"],
            }
            for f in FAMILLES_REVUES
        ],
        "totals": {
            "exceptions": len(exceptions),
            "unreviewed": sum(1 for e in exceptions if e["family"] == "NON_REVU"),
        },
        "exceptions": exceptions,
    }


# ── Validation des deux fichiers exclus du scan ordinaire ───────────────────
#
# `.secrets.baseline` et `SECRET_SCAN_EXCEPTIONS.json` sont retirés des règles
# générales d'entropie pour une raison précise et unique : ils contiennent des
# EMPREINTES de secrets, et un scanner qui les relit signale ses propres
# empreintes à l'infini. Cette exclusion ne dit rien de leur contenu.
#
# Sans contrepartie, elle ouvrirait le trou exact qu'elle prétend éviter : deux
# fichiers versionnés, lus par personne, où l'on peut écrire n'importe quoi.
# D'où ce validateur spécialisé — plus strict que le scan ordinaire, parce qu'il
# connaît le schéma attendu et refuse tout ce qui n'y appartient pas.
#
# Il ne s'appuie sur aucune exemption du genre « c'est dans docs/, donc c'est
# documentaire » : un chemin ne rend pas un contenu inoffensif.

#: Noms de champs qui, dans un rapport de scanner, portent la valeur détectée.
#: Aucun n'a de raison d'exister dans un registre d'empreintes.
CHAMPS_PORTEURS_DE_VALEUR = frozenset({"secret", "match", "value", "raw", "plaintext"})

#: Champs autorisés dans une entrée du registre. Tout autre champ est refusé :
#: un schéma ouvert finirait par accueillir la valeur qu'on prétend exclure.
CHAMPS_EXCEPTION = frozenset(
    {
        "scanner",
        "path",
        "rule",
        "fingerprint",
        "start_line",
        "scope",
        "commit",
        "family",
        "character",
        "rotation_required",
        "justification",
        "occurrences",
    }
)

CHAMPS_EXCEPTION_REQUIS = ("scanner", "path", "rule", "fingerprint", "family", "justification")

#: Motifs de valeurs qui ne doivent jamais apparaître dans ces deux fichiers.
_MOTIFS_INTERDITS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CLE_PRIVEE_PEM", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("CLE_AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("JETON_GITHUB", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("CLE_GOOGLE", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("CLE_SLACK", re.compile(r"\bxox[abporsp]-[0-9A-Za-z-]{10,}\b")),
    ("URL_AVEC_IDENTIFIANTS", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
    ("ADRESSE_ELECTRONIQUE", re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")),
)

#: Format des empreintes acceptées.
#: - detect-secrets : SHA-1 hexadécimal de 40 caractères.
#: - Gitleaks : `commit:fichier:règle:ligne`, ou `fichier:règle:ligne` sur un
#:   scan d'arbre. Le dernier segment est toujours un numéro de ligne.
_EMPREINTE_DETECT_SECRETS = re.compile(r"^[0-9a-f]{40}$")
#: Gitleaks omet le commit sur un scan d'arbre : `fichier:regle:ligne`, trois
#: segments. Sur un scan d'historique il le prefixe : `commit:fichier:regle:ligne`,
#: quatre. Exiger quatre segments a fait echouer la validation des deux entrees
#: d'arbre — le validateur a attrape une erreur de cette expression elle-meme.
_EMPREINTE_GITLEAKS = re.compile(r"^(?:[0-9a-f]{40}:)?[^:]+:[^:]+:\d+$")


def _valeurs_texte(noeud: Any, chemin: str = "") -> Iterator[tuple[str, str]]:
    """Chaque chaîne d'un document JSON, avec le chemin qui y mène."""
    if isinstance(noeud, str):
        yield chemin, noeud
    elif isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            yield from _valeurs_texte(valeur, f"{chemin}.{cle}" if chemin else str(cle))
    elif isinstance(noeud, list):
        for rang, element in enumerate(noeud):
            yield from _valeurs_texte(element, f"{chemin}[{rang}]")


def _champs_porteurs(noeud: Any, chemin: str = "") -> Iterator[str]:
    """Les emplacements dont le NOM annonce une valeur détectée."""
    if isinstance(noeud, dict):
        for cle, valeur in noeud.items():
            ici = f"{chemin}.{cle}" if chemin else str(cle)
            if str(cle).strip().lower() in CHAMPS_PORTEURS_DE_VALEUR:
                yield ici
            yield from _champs_porteurs(valeur, ici)
    elif isinstance(noeud, list):
        for rang, element in enumerate(noeud):
            yield from _champs_porteurs(element, f"{chemin}[{rang}]")


def _empreinte_valide(scanner: str, empreinte: str) -> bool:
    if scanner == "detect-secrets":
        return bool(_EMPREINTE_DETECT_SECRETS.match(empreinte))
    return bool(_EMPREINTE_GITLEAKS.match(empreinte))


def fichiers_de_provenance() -> list[Path]:
    """Les fichiers de provenance G0 soustraits aux règles d'entropie."""
    trouves: set[Path] = set()
    for motif in MOTIFS_FICHIERS_EXCLUS:
        trouves.update(c for c in RACINE.glob(motif) if c.is_file())
    return sorted(trouves, key=lambda c: c.relative_to(RACINE).as_posix())


def valider_fichiers_de_gouvernance() -> list[str]:
    """Les manquements des deux fichiers soustraits au scan ordinaire.

    Renvoie la liste des motifs de refus ; vide, elle vaut acceptation.
    """
    manquements: list[str] = []

    for fichier in [BASELINE, REGISTRE, *fichiers_de_provenance()]:
        if not fichier.is_file():
            manquements.append(f"{fichier.name} : absent")
            continue
        try:
            document = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erreur:
            manquements.append(f"{fichier.name} : illisible — {type(erreur).__name__}")
            continue

        for emplacement in _champs_porteurs(document):
            manquements.append(f"{fichier.name} : champ porteur de valeur interdit — {emplacement}")
        for emplacement, texte in _valeurs_texte(document):
            for nom, motif in _MOTIFS_INTERDITS:
                if motif.search(texte):
                    manquements.append(f"{fichier.name} : {nom} en {emplacement}")

    if REGISTRE.is_file():
        manquements.extend(_valider_registre(json.loads(REGISTRE.read_text(encoding="utf-8"))))
    return manquements


def _valider_registre(registre: dict[str, Any]) -> list[str]:
    """Le schéma du registre d'exceptions, champ par champ."""
    manquements: list[str] = []
    for cle in ("review_commit", "families", "totals", "exceptions"):
        if cle not in registre:
            manquements.append(f"SECRET_SCAN_EXCEPTIONS.json : clé absente — {cle}")
    if manquements:
        return manquements

    exceptions = registre["exceptions"]
    if not isinstance(exceptions, list):
        return ["SECRET_SCAN_EXCEPTIONS.json : `exceptions` n'est pas une liste"]

    vues: set[tuple[str, str, str, str]] = set()
    for rang, entree in enumerate(exceptions):
        prefixe = f"SECRET_SCAN_EXCEPTIONS.json[{rang}]"
        if not isinstance(entree, dict):
            manquements.append(f"{prefixe} : n'est pas un objet")
            continue
        inconnus = set(entree) - CHAMPS_EXCEPTION
        if inconnus:
            manquements.append(f"{prefixe} : champs hors schéma — {sorted(inconnus)}")
        for champ in CHAMPS_EXCEPTION_REQUIS:
            if not str(entree.get(champ, "") or "").strip():
                manquements.append(f"{prefixe} : champ requis vide — {champ}")
        if not isinstance(entree.get("rotation_required", False), bool):
            manquements.append(f"{prefixe} : `rotation_required` n'est pas un booléen")
        if "start_line" in entree and not isinstance(entree["start_line"], int):
            manquements.append(f"{prefixe} : `start_line` n'est pas un entier")

        scanner = str(entree.get("scanner", ""))
        empreinte = str(entree.get("fingerprint", "") or "")
        if empreinte and not _empreinte_valide(scanner, empreinte):
            manquements.append(f"{prefixe} : empreinte au format invalide pour {scanner}")
        if str(entree.get("family", "")) == "NON_REVU":
            manquements.append(f"{prefixe} : famille NON_REVU — décision humaine manquante")
        if len(str(entree.get("justification", ""))) < 20:
            manquements.append(f"{prefixe} : justification trop courte pour valoir décision")

        cle = (scanner, str(entree.get("path", "")), str(entree.get("rule", "")), empreinte)
        if cle in vues:
            manquements.append(f"{prefixe} : identité en double — {empreinte}")
        vues.add(cle)

    annonce = registre.get("totals", {}).get("exceptions")
    if annonce != len(exceptions):
        manquements.append(
            f"SECRET_SCAN_EXCEPTIONS.json : totals.exceptions={annonce} "
            f"ne correspond pas aux {len(exceptions)} entrées"
        )
    return manquements


# ── Réconciliation du scan d'historique ─────────────────────────────────────


def reconcilier_historique(
    detections_historique: list[dict[str, Any]], comptes: dict[str, Any]
) -> dict[str, Any]:
    """Confronte ce que Gitleaks dit avoir parcouru à ce que le dépôt contient.

    Un scan d'historique n'a de valeur que si l'on sait sur quoi il a porté. Le
    rapport précédent avançait deux nombres — 445 commits accessibles, 367
    parcourus — sans relier l'un à l'autre. Un écart de 78 commits inexpliqué
    n'est pas une preuve de couverture : c'est une question ouverte.

    Gitleaks ne parcourt pas les commits de fusion, qui n'introduisent aucun
    contenu propre. Cette fonction vérifie que la partition tombe juste ; si
    elle ne tombe pas juste, ou si le clone est superficiel, elle le dit sous le
    code `HISTORY_SCAN_COUNT_UNRECONCILED` plutôt que d'inventer une raison.

    Les comptages viennent du workflow, qui a git sous la main. Les calculer
    ici obligerait cette barrière à lancer des sous-processus, ce qu'elle
    s'interdit.
    """
    accessibles = int(comptes.get("reachable_commits", 0))
    fusions = int(comptes.get("merge_commits", 0))
    hors_fusion = int(comptes.get("non_merge_commits", 0))
    superficiel = bool(comptes.get("is_shallow_repository", False))
    commits_dans_findings = sorted(
        {str(d.get("commit", "") or "") for d in detections_historique if d.get("commit")}
    )
    reconcilie = accessibles > 0 and accessibles == fusions + hors_fusion

    return {
        "reachable_commits": accessibles,
        "merge_commits": fusions,
        "non_merge_commits": hors_fusion,
        "empty_or_non_diff_commits": int(comptes.get("empty_or_non_diff_commits", 0)),
        "gitleaks_expected_commits_scanned": hors_fusion,
        "distinct_commits_present_in_findings": len(commits_dans_findings),
        "scan_command": str(comptes.get("scan_command", "")),
        "log_opts": str(comptes.get("log_opts", "")),
        "is_shallow_repository": superficiel,
        "reconciled": reconcilie and not superficiel,
        "status": (
            "HISTORY_SCAN_COUNT_RECONCILED"
            if (reconcilie and not superficiel)
            else "HISTORY_SCAN_COUNT_UNRECONCILED"
        ),
    }


# ── Couverture des deux catégories de commits ───────────────────────────────
#
# `reachable = merges + non_merges` est une identité arithmétique. Elle dit que
# la partition est cohérente ; elle ne dit RIEN sur ce qui a été lu.
#
# Gitleaks s'appuie sur `git log -p`. Or `git log -p` n'émet **aucun patch**
# pour un commit de fusion, sauf à lui passer `-m` ou `--cc`. Un contenu
# introduit pendant une résolution de conflit — donc absent des deux parents —
# n'apparaît alors dans aucun patch : ni dans celui de la fusion, qui n'existe
# pas, ni dans ceux des parents, qui ne le contiennent pas.
#
# Mesuré sur un dépôt jetable, une valeur présente uniquement dans l'arbre d'un
# commit de fusion :
#
#     --all                    ABSENT      <- la commande d'origine
#     --all --no-merges        ABSENT
#     --all --merges           ABSENT      <- les fusions sans patch
#     --all --merges -m        DETECTE
#     --all --merges --cc      DETECTE
#
# Il faut donc DEUX preuves distinctes, et non une addition qui tombe juste.

#: Verdicts possibles de la couverture d'historique.
COUVERTURE_ORDINAIRE_VERIFIEE = "NON_MERGE_HISTORY_SCAN_VERIFIED"
COUVERTURE_FUSION_VERIFIEE = "MERGE_HISTORY_SCAN_VERIFIED"
COUVERTURE_FUSION_INCOMPLETE = "MERGE_HISTORY_SCAN_INCOMPLETE"


def couverture_historique(comptes: dict[str, Any], sondes: list[dict[str, Any]]) -> dict[str, Any]:
    """Ce qui a réellement été lu, catégorie par catégorie.

    Deux scans, deux sondes, deux verdicts. Une sonde qui n'a pas détecté sa
    sentinelle rend la catégorie correspondante incomplète, quel que soit le
    nombre de commits annoncé : un scan qui ne trouve pas ce qu'on y a mis ne
    prouve pas ce qu'il n'a pas trouvé.
    """
    par_portee = {s.get("scope"): s for s in sondes if s.get("scope")}
    ordinaire = par_portee.get("non_merge_history", {})
    fusion = par_portee.get("merge_history", {})

    ordinaire_ok = (
        bool(comptes.get("ordinary_history_scan_executed"))
        and ordinaire.get("positive") == "POSITIVE_PROBE_DETECTED"
    )
    fusion_ok = (
        bool(comptes.get("merge_history_scan_executed"))
        and fusion.get("positive") == "POSITIVE_PROBE_DETECTED"
    )
    erreurs = list(comptes.get("history_scan_errors") or [])

    statuts = []
    if ordinaire_ok:
        statuts.append(COUVERTURE_ORDINAIRE_VERIFIEE)
    if fusion_ok:
        statuts.append(COUVERTURE_FUSION_VERIFIEE)
    elif comptes.get("merge_commits", 0):
        statuts.append(COUVERTURE_FUSION_INCOMPLETE)

    return {
        "ordinary_history_scan_executed": bool(comptes.get("ordinary_history_scan_executed")),
        "merge_history_scan_executed": bool(comptes.get("merge_history_scan_executed")),
        "ordinary_history_probe_detected": ordinaire.get("positive") == "POSITIVE_PROBE_DETECTED",
        "merge_resolution_probe_detected": fusion.get("positive") == "POSITIVE_PROBE_DETECTED",
        "merge_scan_log_opts": str(comptes.get("merge_scan_log_opts", "")),
        "ordinary_scan_log_opts": str(comptes.get("ordinary_scan_log_opts", "")),
        "history_scan_errors": erreurs,
        "statuses": statuts,
        "complete": ordinaire_ok and fusion_ok and not erreurs,
    }


# ── Sondes de non-vacuité ───────────────────────────────────────────────────


def sonde_detect_secrets() -> dict[str, Any]:
    """Un scanner qui ne trouve jamais rien est indiscernable d'un scanner vert.

    Deux fichiers sont écrits dans un répertoire temporaire **hors du dépôt** :
    l'un porte la sentinelle et doit être détecté, l'autre est propre et ne doit
    pas l'être. Les deux verdicts sont enregistrés. Le répertoire est détruit.
    """
    with tempfile.TemporaryDirectory(prefix="g0-sonde-secrets-") as repertoire:
        base = Path(repertoire)
        (base / "porteur.txt").write_text(contenu_porteur(), encoding="utf-8")
        (base / "propre.txt").write_text(TEXTE_PROPRE, encoding="utf-8")
        detections, _ = scanner_arbre(["porteur.txt", "propre.txt"], racine=base)
    porteur = [d for d in detections if d["path"] == "porteur.txt"]
    propre = [d for d in detections if d["path"] == "propre.txt"]
    return {
        "scanner": "detect-secrets",
        "positive": "POSITIVE_PROBE_DETECTED" if porteur else "POSITIVE_PROBE_MISSED",
        "negative": "NEGATIVE_PROBE_ACCEPTED" if not propre else "NEGATIVE_PROBE_FALSE_POSITIVE",
        "positive_rules": sorted({d["rule"] for d in porteur}),
    }


def verifier_sondes_gitleaks(
    rapport_porteur: Path, rapport_propre: Path, portee: str = "tree"
) -> dict[str, Any]:
    """Le même contrôle pour Gitleaks, sur les rapports produits par le workflow.

    Le dépôt jetable est créé par le job, hors du dépôt principal. Ce sont les
    deux rapports qui sont jugés ici — jamais les valeurs.

    `portee` distingue les sondes : `non_merge_history` pour un secret ajouté
    puis supprimé hors de toute fusion, `merge_history` pour un secret présent
    uniquement dans l'arbre d'un commit de fusion. Sans cette distinction, une
    sonde réussie couvrirait l'autre catégorie sans l'avoir exercée.
    """
    porteur = lire_rapport_gitleaks(rapport_porteur, "sonde")
    propre = lire_rapport_gitleaks(rapport_propre, "sonde")
    return {
        "scanner": "gitleaks",
        "scope": portee,
        "positive": "POSITIVE_PROBE_DETECTED" if porteur else "POSITIVE_PROBE_MISSED",
        "negative": "NEGATIVE_PROBE_ACCEPTED" if not propre else "NEGATIVE_PROBE_FALSE_POSITIVE",
        "positive_rules": sorted({d["rule"] for d in porteur}),
    }


#: Les seuls noms d'outil qu'une sonde peut porter.
OUTILS = ("detect-secrets", "gitleaks")


def _outil(valeur: Any) -> str:
    """Le nom de l'outil sondé, ou une constante d'erreur — jamais autre chose.

    La constante RENVOYÉE est celle du tuple, pas la valeur reçue. La différence
    n'est pas cosmétique : `str(valeur) if valeur in OUTILS` restitue l'objet
    d'entrée, donc la donnée continue de circuler. Renvoyer l'élément du tuple
    coupe le flux — ce que CodeQL a signalé deux fois avant que ce soit corrigé.
    """
    for connu in OUTILS:
        if valeur == connu:
            return connu
    return "OUTIL_INCONNU"


#: Les seuls verdicts qu'une sonde peut rendre. Rien d'autre n'est affichable.
VERDICTS = (
    "POSITIVE_PROBE_DETECTED",
    "POSITIVE_PROBE_MISSED",
    "NEGATIVE_PROBE_ACCEPTED",
    "NEGATIVE_PROBE_FALSE_POSITIVE",
)


def _verdict(valeur: Any) -> str:
    """Le verdict d'une sonde, ou une constante d'erreur — jamais autre chose.

    Comme `_outil`, cette fonction renvoie la constante du tuple et non la
    valeur reçue : c'est ce qui coupe réellement le flux de données.
    """
    for connu in VERDICTS:
        if valeur == connu:
            return connu
    return "VERDICT_INCONNU"


def sondes_concluantes(sondes: list[dict[str, Any]]) -> bool:
    return all(
        s["positive"] == "POSITIVE_PROBE_DETECTED" and s["negative"] == "NEGATIVE_PROBE_ACCEPTED"
        for s in sondes
    )


# ── Ligne de commande ───────────────────────────────────────────────────────


def _resume(titre: str, detections: list[dict[str, Any]]) -> None:
    print(f"{titre} : {len(detections)} détection(s)")
    par_regle: dict[str, int] = {}
    for detection in detections:
        par_regle[detection["rule"]] = par_regle.get(detection["rule"], 0) + 1
    for regle, total in sorted(par_regle.items()):
        print(f"    {regle:32s} {total}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Barrière de secrets G0.")
    parser.add_argument("--files-from", type=Path, help="liste de chemins (sortie de git ls-files)")
    parser.add_argument("--tree", action="store_true", help="scanne l'arbre courant")
    parser.add_argument("--gitleaks-dir-report", type=Path, help="rapport Gitleaks de l'arbre")
    parser.add_argument(
        "--gitleaks-git-report",
        type=Path,
        help="rapport Gitleaks de l'historique ORDINAIRE (--all --no-merges)",
    )
    parser.add_argument(
        "--gitleaks-merge-history-report",
        type=Path,
        help=(
            "rapport Gitleaks des RESOLUTIONS DE FUSION. `git log -p` n'emet aucun "
            "patch pour un commit de fusion sans `-m` ni `--cc` : un contenu propre a "
            "la resolution echappe sinon aux deux scans."
        ),
    )
    parser.add_argument("--gitleaks-merge-probe-positive", type=Path)
    parser.add_argument("--gitleaks-merge-probe-negative", type=Path)
    parser.add_argument("--probes", action="store_true", help="exécute la sonde detect-secrets")
    parser.add_argument("--gitleaks-probe-positive", type=Path)
    parser.add_argument("--gitleaks-probe-negative", type=Path)
    parser.add_argument(
        "--history-counts",
        type=Path,
        help=(
            "JSON des comptages de commits produit par le workflow. Sans lui, la "
            "couverture de l'historique ne peut pas être réconciliée, et le statut "
            "HISTORY_SCAN_COUNT_UNRECONCILED est émis."
        ),
    )
    parser.add_argument("--report", type=Path, help="écrit un rapport expurgé")
    parser.add_argument("--propose", type=Path, help="écrit une proposition de registre")
    parser.add_argument(
        "--uncovered-from",
        type=Path,
        help=(
            "rapport expurgé d'une exécution précédente : ses détections non "
            "couvertes sont réinjectées dans --propose. Les scans Gitleaks ne "
            "tournent qu'en CI ; sans cela, le registre serait complété de "
            "mémoire au lieu d'être dérivé d'une mesure."
        ),
    )
    args = parser.parse_args(argv)

    connues, chemins_non_posix = charger_baseline()
    if chemins_non_posix:
        print(
            f"NOTE : {len(chemins_non_posix)} chemin(s) de .secrets.baseline portent des "
            "séparateurs Windows et ont été normalisés à la lecture. Le fichier n'est pas "
            "modifié : le défaut est un constat du lot B."
        )

    detections: list[dict[str, Any]] = []
    rapport_scan: dict[str, Any] = {}
    reconciliation: dict[str, Any] = {}
    comptes_historique: dict[str, Any] = {}
    if args.tree:
        chemins = fichiers_a_scanner(args.files_from)
        print(f"Fichiers scannés (arbre courant) : {len(chemins)}")
        arbre, rapport_scan = scanner_arbre(chemins)
        print(
            f"    tentés {rapport_scan['attempted_files']} · "
            f"scannés {rapport_scan['successfully_scanned_files']} · "
            f"exclus {rapport_scan['explicitly_excluded_files']} · "
            f"erreurs {len(rapport_scan['scan_errors'])}"
        )
        _resume("Arbre courant", arbre)
        detections.extend(arbre)
    try:
        if args.gitleaks_dir_report:
            gl_arbre = lire_rapport_gitleaks(args.gitleaks_dir_report, "arbre")
            _resume("Gitleaks — arbre courant", gl_arbre)
            detections.extend(gl_arbre)
        if args.gitleaks_git_report:
            gl_git = lire_rapport_gitleaks(args.gitleaks_git_report, "historique")
            _resume("Gitleaks — historique complet", gl_git)
            detections.extend(gl_git)
            comptes_historique = (
                json.loads(args.history_counts.read_text(encoding="utf-8"))
                if args.history_counts and args.history_counts.is_file()
                else {}
            )
            reconciliation = reconcilier_historique(gl_git, comptes_historique)
        if args.gitleaks_merge_history_report:
            gl_fusion = lire_rapport_gitleaks(args.gitleaks_merge_history_report, "merge-history")
            _resume("Gitleaks — resolutions de fusion", gl_fusion)
            detections.extend(gl_fusion)
            print(
                f"Historique : {reconciliation['reachable_commits']} accessibles = "
                f"{reconciliation['merge_commits']} fusions + "
                f"{reconciliation['non_merge_commits']} hors fusion → "
                f"{reconciliation['status']}"
            )
    except DetectionSansEmpreinte as erreur:
        print(f"\nECHEC : {erreur}", file=sys.stderr)
        return 1

    if args.uncovered_from:
        rapport = json.loads(args.uncovered_from.read_text(encoding="utf-8"))
        reinjectees = [d for d in rapport.get("uncovered", []) if not exclu_du_scan(d["path"])]
        print(f"Détections réinjectées depuis un rapport mesuré : {len(reinjectees)}")
        detections.extend(reinjectees)

    if args.propose:
        proposition = proposer(
            detections, charger_registre() if REGISTRE.is_file() else {}, connues
        )
        args.propose.write_text(
            json.dumps(proposition, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Proposition écrite dans {args.propose} — à relire avant de la versionner.")
        return 0

    sondes: list[dict[str, Any]] = []
    if args.probes:
        sondes.append(sonde_detect_secrets())
    if args.gitleaks_probe_positive and args.gitleaks_probe_negative:
        sondes.append(
            verifier_sondes_gitleaks(
                args.gitleaks_probe_positive,
                args.gitleaks_probe_negative,
                portee="non_merge_history",
            )
        )
    if args.gitleaks_merge_probe_positive and args.gitleaks_merge_probe_negative:
        sondes.append(
            verifier_sondes_gitleaks(
                args.gitleaks_merge_probe_positive,
                args.gitleaks_merge_probe_negative,
                portee="merge_history",
            )
        )
    for sonde in sondes:
        # Seuls des verdicts appartenant a l'ensemble ferme ci-dessus sont
        # affiches. Ce n'est pas une precaution de style : CodeQL relevait ici
        # une journalisation de donnee sensible, parce que la structure vient
        # d'un scan de secrets. Le controle d'appartenance garantit que rien
        # d'autre qu'une des six constantes ne peut sortir.
        outil = _outil(sonde["scanner"])
        positif = _verdict(sonde["positive"])
        negatif = _verdict(sonde["negative"])
        print(f"Sonde {outil} : {positif} / {negatif}")

    # Les deux fichiers soustraits aux règles d'entropie sont relus ici, par un
    # validateur qui connaît leur schéma. Sans lui, l'exclusion technique
    # deviendrait une zone franche.
    manquements_gouvernance = valider_fichiers_de_gouvernance()
    couverture = couverture_historique(comptes_historique, sondes) if comptes_historique else {}
    if couverture:
        print(
            "Couverture d'historique : "
            + (" · ".join(couverture["statuses"]) or "aucune categorie verifiee")
        )

    try:
        confrontation = confronter(detections, connues, charger_registre())
    except DetectionSansEmpreinte as erreur:
        print(f"\nECHEC : {erreur}", file=sys.stderr)
        return 1
    residus = confrontation["residus"]

    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "totals": {
                        "detections": len(detections),
                        "covered": len(confrontation["couvertes"]),
                        "uncovered": len(residus),
                    },
                    "probes": sondes,
                    "uncovered": residus,
                    "baseline_paths_normalised": chemins_non_posix,
                    "tree_scan": rapport_scan,
                    "history_reconciliation": reconciliation,
                    "history_coverage": couverture,
                    "governance_files_validation": manquements_gouvernance,
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Rapport expurgé écrit dans {args.report}")

    echec = False
    if residus:
        echec = True
        print(f"\nECHEC : {len(residus)} détection(s) sans couverture écrite.", file=sys.stderr)
        for detection in residus[:200]:
            print(
                f"  ! {detection['scanner']} {detection['path']} "
                f"[{detection['rule']}] {detection['fingerprint']}",
                file=sys.stderr,
            )
        print(
            "\nAucune valeur n'est affichée. Qualifier chaque emplacement, puis "
            "l'inscrire dans docs/governance/SECRET_SCAN_EXCEPTIONS.json.",
            file=sys.stderr,
        )
    if sondes and not sondes_concluantes(sondes):
        echec = True
        print(
            "\nECHEC : une sonde de non-vacuité n'a pas rendu le verdict attendu. "
            "Un scanner qui ne détecte plus la sentinelle ne prouve rien.",
            file=sys.stderr,
        )
    if rapport_scan and not rapport_scan["complete"]:
        echec = True
        print(
            f"\nECHEC — SECRET_SCAN_INCOMPLETE : {len(rapport_scan['scan_errors'])} fichier(s) "
            "suivi(s) n'ont été ni scannés ni explicitement exclus. Un fichier illisible n'est "
            "pas un fichier propre.",
            file=sys.stderr,
        )
        for erreur in rapport_scan["scan_errors"][:50]:
            print(f"  ! {erreur['path']} — {erreur['reason']}", file=sys.stderr)
    if manquements_gouvernance:
        echec = True
        print(
            f"\nECHEC : {len(manquements_gouvernance)} manquement(s) dans les fichiers exclus "
            "du scan ordinaire. Leur exclusion n'est justifiée que par la récursion des "
            "empreintes ; elle ne les dispense pas d'être relus.",
            file=sys.stderr,
        )
        for manquement in manquements_gouvernance[:50]:
            print(f"  ! {manquement}", file=sys.stderr)
    if couverture and not couverture["complete"]:
        echec = True
        manquantes = []
        if not couverture["ordinary_history_scan_executed"]:
            manquantes.append("le scan de l'historique ordinaire n'a pas ete execute")
        elif not couverture["ordinary_history_probe_detected"]:
            manquantes.append("la sonde de l'historique ordinaire n'a rien detecte")
        if not couverture["merge_history_scan_executed"]:
            manquantes.append("le scan des resolutions de fusion n'a pas ete execute")
        elif not couverture["merge_resolution_probe_detected"]:
            manquantes.append(
                "la sonde de resolution de fusion n'a rien detecte — "
                "`git log -p` n'emet aucun patch pour une fusion sans `-m` ni `--cc`"
            )
        for erreur in couverture["history_scan_errors"]:
            manquantes.append(f"erreur Git pendant le scan : {erreur}")
        print(
            "\nECHEC — "
            + (" · ".join(couverture["statuses"]) or "MERGE_HISTORY_SCAN_INCOMPLETE")
            + " : "
            "une categorie de commits n'est pas demontree lue.",
            file=sys.stderr,
        )
        for manque in manquantes:
            print(f"  ! {manque}", file=sys.stderr)
    if reconciliation and not reconciliation["reconciled"]:
        echec = True
        print(
            f"\nECHEC — {reconciliation['status']} : le nombre de commits parcourus par le "
            "scan d'historique ne se relie pas aux commits accessibles. Un scan dont on ne "
            "sait pas sur quoi il a porté ne prouve pas la couverture de l'historique.",
            file=sys.stderr,
        )
    if echec:
        return 1

    print(f"\n{len(detections)} détection(s), toutes couvertes par écrit.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

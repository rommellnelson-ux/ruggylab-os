"""Barrière de secrets G0 — bloquante, sur l'arbre courant et sur l'historique.

Pourquoi ce script existe alors que `detect-secrets` a déjà une commande.

1. **La commande seule ne peut pas bloquer aujourd'hui.** `.secrets.baseline`
   couvre 14 fichiers ; l'arbre en compte 77 qui déclenchent une règle. Le
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
circulent le chemin, la règle déclenchée, l'empreinte (SHA-1 calculé par
`detect-secrets`, ou le couple règle/commit pour Gitleaks) et le jugement
enregistré. Un fragment de secret reste un indice.

**Le registre d'exceptions ne se remplit pas tout seul.** `--propose` écrit une
proposition à partir de familles de chemins *écrites à la main* dans
`FAMILLES_REVUES` ; un chemin qui n'appartient à aucune famille revue sort en
`NON_REVU`, et la barrière le refuse. Accepter automatiquement tout ce qui est
trouvé aurait produit un registre qui dit oui à tout.

Aucun sous-processus : les rapports Gitleaks sont produits par le workflow et
lus ici. Aucun appel réseau. Aucune donnée patient.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import tempfile
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
SENTINELLE_SONDE = "AK" + "IA" + "G0PROBE" + "SENTINEL7"

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
    retenus = [
        c
        for c in chemins
        if Path(c).suffix.lower() not in SUFFIXES_EXCLUS and c not in FICHIERS_EXCLUS
    ]
    return sorted(set(retenus))


# ── Scan de l'arbre courant ─────────────────────────────────────────────────


def scanner_arbre(chemins: list[str], racine: Path | None = None) -> list[dict[str, Any]]:
    """Les détections `detect-secrets` de l'arbre, sans aucune valeur.

    `secret_hash` est le SHA-1 que `detect-secrets` calcule sur la valeur : il
    identifie une occurrence sans la révéler, et c'est lui qui sert de clé au
    registre d'exceptions.
    """
    from detect_secrets.core import scan
    from detect_secrets.settings import transient_settings

    base = racine or RACINE
    trouvees: list[dict[str, Any]] = []
    with transient_settings(configuration_scan()):
        for chemin in chemins:
            absolu = base / chemin
            if not absolu.is_file():
                continue
            try:
                detections = list(scan.scan_file(str(absolu)))
            except (OSError, UnicodeDecodeError):
                continue
            for detection in detections:
                trouvees.append(
                    {
                        "scanner": "detect-secrets",
                        "path": chemin,
                        "rule": detection.type,
                        "fingerprint": detection.secret_hash,
                    }
                )
    return sorted(trouvees, key=lambda t: (t["path"], t["rule"], t["fingerprint"]))


# ── Lecture des rapports Gitleaks ───────────────────────────────────────────


def lire_rapport_gitleaks(chemin: Path, portee: str) -> list[dict[str, Any]]:
    """Les détections d'un rapport Gitleaks JSON, réduites à ce qui ne fuit pas.

    Gitleaks est appelé avec `--redact` : les champs `Secret` et `Match` sont
    déjà remplacés côté outil. Ce lecteur ne les recopie pas pour autant — il ne
    retient que le chemin, la règle et, pour l'historique, le commit.
    """
    if not chemin.is_file():
        raise SystemExit(f"rapport Gitleaks absent : {chemin}")
    texte = chemin.read_text(encoding="utf-8").strip()
    brut = json.loads(texte) if texte else []
    detections: list[dict[str, Any]] = []
    for element in brut:
        detections.append(
            {
                "scanner": f"gitleaks-{portee}",
                "path": str(element.get("File", "")).replace("\\", "/"),
                "rule": str(element.get("RuleID", "")),
                "fingerprint": str(element.get("Commit", "")) or "arbre-courant",
            }
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
    return (
        detection["scanner"],
        detection["path"],
        detection["rule"],
        detection["fingerprint"],
    )


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
                "commit": (precedente or {}).get("commit", registre_courant.get("review_commit")),
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
    exceptions.sort(key=lambda e: (e["scanner"], e["path"], e["rule"], e["fingerprint"]))
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


# ── Sondes de non-vacuité ───────────────────────────────────────────────────


def sonde_detect_secrets() -> dict[str, Any]:
    """Un scanner qui ne trouve jamais rien est indiscernable d'un scanner vert.

    Deux fichiers sont écrits dans un répertoire temporaire **hors du dépôt** :
    l'un porte la sentinelle et doit être détecté, l'autre est propre et ne doit
    pas l'être. Les deux verdicts sont enregistrés. Le répertoire est détruit.
    """
    with tempfile.TemporaryDirectory(prefix="g0-sonde-secrets-") as repertoire:
        base = Path(repertoire)
        (base / "porteur.txt").write_text(
            f"aws_access_key_id = {SENTINELLE_SONDE}\n", encoding="utf-8"
        )
        (base / "propre.txt").write_text(TEXTE_PROPRE, encoding="utf-8")
        detections = scanner_arbre(["porteur.txt", "propre.txt"], racine=base)
    porteur = [d for d in detections if d["path"] == "porteur.txt"]
    propre = [d for d in detections if d["path"] == "propre.txt"]
    return {
        "scanner": "detect-secrets",
        "positive": "POSITIVE_PROBE_DETECTED" if porteur else "POSITIVE_PROBE_MISSED",
        "negative": "NEGATIVE_PROBE_ACCEPTED" if not propre else "NEGATIVE_PROBE_FALSE_POSITIVE",
        "positive_rules": sorted({d["rule"] for d in porteur}),
    }


def verifier_sondes_gitleaks(rapport_porteur: Path, rapport_propre: Path) -> dict[str, Any]:
    """Le même contrôle pour Gitleaks, sur les rapports produits par le workflow.

    Le dépôt jetable est créé par le job, hors du dépôt principal, avec un
    commit portant la sentinelle et un commit propre. Ce sont les deux rapports
    qui sont jugés ici — jamais les valeurs.
    """
    porteur = lire_rapport_gitleaks(rapport_porteur, "sonde")
    propre = lire_rapport_gitleaks(rapport_propre, "sonde")
    return {
        "scanner": "gitleaks",
        "positive": "POSITIVE_PROBE_DETECTED" if porteur else "POSITIVE_PROBE_MISSED",
        "negative": "NEGATIVE_PROBE_ACCEPTED" if not propre else "NEGATIVE_PROBE_FALSE_POSITIVE",
        "positive_rules": sorted({d["rule"] for d in porteur}),
    }


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
    parser.add_argument("--gitleaks-git-report", type=Path, help="rapport Gitleaks de l'historique")
    parser.add_argument("--probes", action="store_true", help="exécute la sonde detect-secrets")
    parser.add_argument("--gitleaks-probe-positive", type=Path)
    parser.add_argument("--gitleaks-probe-negative", type=Path)
    parser.add_argument("--report", type=Path, help="écrit un rapport expurgé")
    parser.add_argument("--propose", type=Path, help="écrit une proposition de registre")
    args = parser.parse_args(argv)

    connues, chemins_non_posix = charger_baseline()
    if chemins_non_posix:
        print(
            f"NOTE : {len(chemins_non_posix)} chemin(s) de .secrets.baseline portent des "
            "séparateurs Windows et ont été normalisés à la lecture. Le fichier n'est pas "
            "modifié : le défaut est un constat du lot B."
        )

    detections: list[dict[str, Any]] = []
    if args.tree:
        chemins = fichiers_a_scanner(args.files_from)
        print(f"Fichiers scannés (arbre courant) : {len(chemins)}")
        arbre = scanner_arbre(chemins)
        _resume("Arbre courant", arbre)
        detections.extend(arbre)
    if args.gitleaks_dir_report:
        gl_arbre = lire_rapport_gitleaks(args.gitleaks_dir_report, "arbre")
        _resume("Gitleaks — arbre courant", gl_arbre)
        detections.extend(gl_arbre)
    if args.gitleaks_git_report:
        gl_git = lire_rapport_gitleaks(args.gitleaks_git_report, "historique")
        _resume("Gitleaks — historique complet", gl_git)
        detections.extend(gl_git)

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
            verifier_sondes_gitleaks(args.gitleaks_probe_positive, args.gitleaks_probe_negative)
        )
    for sonde in sondes:
        print(f"Sonde {sonde['scanner']} : {sonde['positive']} / {sonde['negative']}")

    confrontation = confronter(detections, connues, charger_registre())
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
    if echec:
        return 1

    print(f"\n{len(detections)} détection(s), toutes couvertes par écrit.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

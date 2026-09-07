"""Inventaire reproductible des licences des dépendances Python installées.

Repose sur ``importlib.metadata`` seul : pas d'outil tiers à épingler, donc rien
de plus à auditer pour produire l'audit lui-même.

Produit deux sorties :

- ``--json`` : inventaire machine, une entrée par distribution installée ;
- ``--copy-licenses`` : copie les fichiers LICENSE/NOTICE trouvés dans les
  métadonnées de chaque paquet vers ``licenses/third-party/python/<nom>/``.

Les textes sont **copiés depuis le paquet installé**, jamais retéléchargés
depuis une source non officielle : c'est le texte réellement distribué qui fait
foi.

Aucune licence ``UNKNOWN`` n'est masquée : elle est marquée comme telle et
remonte dans le compte des éléments non résolus, ce qui fait échouer la CI de
conformité tant qu'elle n'est pas qualifiée à la main.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

#: Fichiers de licence usuels dans les distributions Python.
_MOTIFS_LICENCE = re.compile(
    r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS|COPYRIGHT)([.\-_][\w.\-]*)?$",
    re.IGNORECASE,
)

#: Ce que l'on considère comme une licence non déterminée.
_INCONNUES = {"", "unknown", "none", "null", "unlicensed"}


def _valeur(meta: metadata.PackageMetadata, cle: str) -> str:
    valeur = meta.get(cle)
    return (valeur or "").strip()


def _licence_declaree(meta: metadata.PackageMetadata) -> str:
    """Licence déclarée : champ `License-Expression`, `License`, ou classifier."""
    for cle in ("License-Expression", "License"):
        valeur = _valeur(meta, cle)
        # Certains paquets collent tout le texte de licence dans `License`.
        if valeur and valeur.lower() not in _INCONNUES and len(valeur) < 200:
            return valeur
    classifiers = [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        # « License :: OSI Approved :: MIT License » -> « MIT License »
        return "; ".join(c.split(" :: ")[-1] for c in classifiers)
    return "UNKNOWN"


def _url(meta: metadata.PackageMetadata) -> str:
    for cle in ("Home-page", "Project-URL"):
        valeur = _valeur(meta, cle)
        if valeur:
            return valeur.split(", ")[-1] if ", " in valeur else valeur
    return ""


def _fichiers_licence(dist: metadata.Distribution) -> list[str]:
    return [str(f) for f in (dist.files or []) if _MOTIFS_LICENCE.search(str(f))]


def _requis_directs(chemin_requirements: Path) -> set[str]:
    """Noms normalisés des dépendances déclarées dans requirements.txt."""
    directs: set[str] = set()
    if not chemin_requirements.is_file():
        return directs
    for ligne in chemin_requirements.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if not ligne or ligne.startswith("-"):
            continue
        nom = re.split(r"[<>=!~\[; ]", ligne, maxsplit=1)[0].strip()
        if nom:
            directs.add(nom.lower().replace("_", "-"))
    return directs


def inventorier(racine: Path) -> list[dict]:
    directs = _requis_directs(racine / "requirements.txt")
    entrees: list[dict] = []
    for dist in metadata.distributions():
        meta = dist.metadata
        nom = _valeur(meta, "Name") or (dist.name or "?")
        licence = _licence_declaree(meta)
        entrees.append(
            {
                "name": nom,
                "version": _valeur(meta, "Version") or (dist.version or "?"),
                "license": licence,
                "license_is_unknown": licence.strip().lower() in _INCONNUES or licence == "UNKNOWN",
                "author": _valeur(meta, "Author") or _valeur(meta, "Maintainer"),
                "url": _url(meta),
                "license_files": _fichiers_licence(dist),
                "direct": nom.lower().replace("_", "-") in directs,
            }
        )
    return sorted(entrees, key=lambda e: e["name"].lower())


def copier_licences(racine: Path, entrees: list[dict]) -> int:
    """Copie les textes de licence depuis les paquets installés. Renvoie le total."""
    cible = racine / "licenses" / "third-party" / "python"
    cible.mkdir(parents=True, exist_ok=True)
    copies = 0
    for entree in entrees:
        if not entree["license_files"]:
            continue
        try:
            dist = metadata.distribution(entree["name"])
        except metadata.PackageNotFoundError:  # pragma: no cover - défensif
            continue
        dossier = cible / entree["name"]
        dossier.mkdir(parents=True, exist_ok=True)
        for relatif in entree["license_files"]:
            source = dist.locate_file(relatif)
            if not Path(source).is_file():
                continue
            shutil.copyfile(source, dossier / Path(relatif).name)
            copies += 1
    return copies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", type=Path, help="écrit l'inventaire JSON ici")
    parser.add_argument("--copy-licenses", action="store_true")
    parser.add_argument(
        "--fail-on-unknown",
        action="store_true",
        help="code de sortie 1 si une licence reste indéterminée",
    )
    args = parser.parse_args(argv)

    entrees = inventorier(args.root)
    inconnues = [e for e in entrees if e["license_is_unknown"]]

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(entrees, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    if args.copy_licenses:
        total = copier_licences(args.root, entrees)
        print(f"Textes de licence copiés : {total}")

    directs = sum(1 for e in entrees if e["direct"])
    print(f"Distributions inventoriées : {len(entrees)} (dont {directs} directes)")
    print(f"Licences indéterminées      : {len(inconnues)}")
    for entree in inconnues:
        print(f"  - {entree['name']} {entree['version']}")

    if inconnues and args.fail_on_unknown:
        print(
            "\nECHEC : une licence indéterminée ne peut pas être acceptée en silence. "
            "La qualifier à la main dans THIRD_PARTY_NOTICES.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

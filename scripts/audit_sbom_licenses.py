"""Audit du SBOM de l'image : aucune licence indéterminée acceptée en silence.

L'inventaire Python (`inventory_python_licenses.py`) ne couvre que les
distributions Python. L'image, elle, embarque en plus la base Debian et tout ce
que les couches y déposent — c'est ce que le SBOM révèle, et c'est ce que l'on
distribue réellement.

Deux contrôles :

1. **Composants sans licence.** Les entrées de type ``file`` sont ignorées : ce
   sont des fichiers catalogués, pas des composants tiers. Tout composant
   *paquet* sans licence doit figurer, qualifié et daté, dans
   ``docs/governance/SBOM_LICENSE_EXCEPTIONS.json``. Sinon : échec.
2. **Recensement copyleft.** Les familles GPL/LGPL/AGPL/MPL présentes sont
   comptées et affichées. Le recensement ne conclut rien : il rend visible ce
   qui doit être qualifié à la main dans ``THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

#: Types d'entrées CycloneDX qui ne sont pas des composants tiers.
_TYPES_IGNORES = {"file"}

#: Familles dont la présence doit rester visible dans le journal de conformité.
_FAMILLES = ("AGPL", "GPL", "LGPL", "MPL", "EPL", "CDDL", "SSPL", "RSAL")


def _licences(composant: dict) -> list[str]:
    valeurs: list[str] = []
    for entree in composant.get("licenses") or []:
        licence = entree.get("license") or {}
        valeur = licence.get("id") or licence.get("name") or entree.get("expression")
        if valeur:
            valeurs.append(valeur)
    return valeurs


def _cle(nom: str, version: str) -> str:
    return f"{nom}@{version}"


def auditer(sbom: dict, exceptions: dict) -> tuple[list[dict], collections.Counter]:
    autorises = {_cle(e["name"], e["version"]) for e in exceptions.get("exceptions", [])}
    non_qualifies: list[dict] = []
    familles: collections.Counter = collections.Counter()

    for composant in sbom.get("components", []):
        if composant.get("type") in _TYPES_IGNORES:
            continue
        valeurs = _licences(composant)
        if not valeurs:
            cle = _cle(composant.get("name", "?"), composant.get("version", "?"))
            if cle not in autorises:
                non_qualifies.append(composant)
            continue
        for valeur in valeurs:
            for famille in _FAMILLES:
                if famille in valeur.upper():
                    familles[valeur] += 1
                    break

    return non_qualifies, familles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path, help="SBOM CycloneDX JSON de l'image")
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=Path("docs/governance/SBOM_LICENSE_EXCEPTIONS.json"),
    )
    args = parser.parse_args(argv)

    sbom = json.loads(args.sbom.read_text(encoding="utf-8"))
    exceptions = json.loads(args.exceptions.read_text(encoding="utf-8"))

    non_qualifies, familles = auditer(sbom, exceptions)

    paquets = [c for c in sbom.get("components", []) if c.get("type") not in _TYPES_IGNORES]
    print(f"Composants (hors entrées de fichier) : {len(paquets)}")

    print("\nLicences copyleft ou particulières recensées dans l'image :")
    if familles:
        for licence, total in familles.most_common():
            print(f"  {total:4d}  {licence}")
    else:
        print("  (aucune)")
    print(
        "\nCe recensement ne conclut rien. Les obligations correspondantes sont\n"
        "qualifiées à la main dans THIRD_PARTY_NOTICES.md."
    )

    if non_qualifies:
        print(
            f"\nECHEC : {len(non_qualifies)} composant(s) sans licence et absent(s) du "
            "registre des exceptions :",
            file=sys.stderr,
        )
        for composant in non_qualifies:
            print(
                f"  - {composant.get('name')} {composant.get('version')} "
                f"({composant.get('purl') or composant.get('type')})",
                file=sys.stderr,
            )
        print(
            "\nQualifier chacun dans docs/governance/SBOM_LICENSE_EXCEPTIONS.json, "
            "ou le retirer de l'image.",
            file=sys.stderr,
        )
        return 1

    print("\nAucune licence indéterminée non qualifiée.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

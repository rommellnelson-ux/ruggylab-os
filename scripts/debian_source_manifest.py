"""Manifeste des paquets Debian de l'image, et de leurs sources correspondantes.

Distribuer une image, c'est distribuer les binaires qu'elle contient. Quand
certains sont sous GPL ou LGPL, une obligation d'**offre du code source
correspondant** s'y attache. Y répondre suppose d'abord de savoir, précisément,
*quels* paquets, dans *quelle* version, viennent de *quelle* source.

Ce script lit l'image **réellement construite** — jamais un fichier de
configuration, jamais une supposition — via ``dpkg-query`` et les fichiers
``copyright`` que Debian installe dans ``/usr/share/doc``.

Trois fichiers sont produits :

``debian-binary-packages.json``
    un paquet binaire par entrée : nom, version, architecture, source et
    version source, taille installée.

``debian-source-packages.json``
    un paquet **source** par entrée, avec les binaires qu'il produit dans
    l'image et l'URL du snapshot immuable qui permet de le récupérer.

``debian-license-manifest.json``
    la licence relevée pour chaque paquet, la présence du fichier ``copyright``,
    la présence du texte de licence référencé, et l'obligation qui en découle.

Le script **ne conclut rien juridiquement**. Il établit un constat vérifiable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

#: Snapshot Debian : archive immuable et datée, contrairement aux miroirs
#: courants où une version disparaît dès qu'elle est remplacée.
SNAPSHOT = "https://snapshot.debian.org"

#: Familles de licences qui portent une obligation de source correspondante.
_COPYLEFT = ("GPL", "LGPL", "AGPL", "MPL", "EPL", "CDDL")

#: Répertoire des textes de licence référencés par les fichiers copyright.
_COMMON = "/usr/share/common-licenses"

#: Référence à un texte de licence dans un fichier copyright Debian.
#
# Le nom NE DOIT PAS se terminer par un point : les fichiers copyright écrivent
# « voir /usr/share/common-licenses/GPL-2. », et une expression trop gourmande
# capturerait le point final de la phrase. On lirait alors « GPL-2. », absent du
# répertoire, et le manifeste signalerait un texte manquant qui ne l'est pas.
# Les apostrophes typographiques fermantes sont exclues pour la même raison.
_REFERENCE_LICENCE = re.compile(re.escape(_COMMON) + r"/([A-Za-z0-9+\-]+(?:\.[A-Za-z0-9+\-]+)*)")

#: Champs demandés à dpkg, séparés par des tabulations.
_CHAMPS_DPKG = (
    r"${Package}\t${Version}\t${Architecture}\t"
    r"${source:Package}\t${source:Version}\t${Installed-Size}\n"
)


def _dans_image(image: str, commande: str) -> str:
    """Exécute une commande shell DANS l'image et renvoie sa sortie."""
    resultat = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", commande],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"échec dans l'image : {resultat.stderr.strip()[:400]}")
    return resultat.stdout


def paquets_binaires(image: str) -> list[dict]:
    """Inventaire dpkg de l'image, avec le paquet source de chaque binaire."""
    # Guillemets SIMPLES obligatoires : `sh` interpréterait `${Package}` comme
    # une variable shell entre guillemets doubles, et échouerait sur une
    # « Bad substitution ». Ici, la substitution est celle de dpkg, pas du shell.
    sortie = _dans_image(image, f"dpkg-query -W -f='{_CHAMPS_DPKG}'")
    entrees: list[dict] = []
    for ligne in sortie.splitlines():
        if not ligne.strip():
            continue
        colonnes = ligne.split("\t")
        if len(colonnes) < 6:
            continue
        nom, version, arch, source, version_source, taille = colonnes[:6]
        entrees.append(
            {
                "binary_package": nom,
                "version": version,
                "architecture": arch,
                # dpkg laisse `source:Package` vide quand il est identique au
                # nom du binaire : le rendre explicite évite un trou de manifeste.
                "source_package": source or nom,
                "source_version": version_source or version,
                "installed_size_kb": int(taille) if taille.isdigit() else None,
            }
        )
    return sorted(entrees, key=lambda e: e["binary_package"])


def _licence_du_copyright(texte: str) -> list[str]:
    """Licences déclarées dans un fichier copyright Debian.

    Le format DEP-5 porte des champs ``License:`` machine-lisibles. Beaucoup de
    paquets restent en format libre : on retombe alors sur les textes référencés
    dans ``/usr/share/common-licenses``, ce qui est un indice, pas une preuve.
    """
    licences = {
        valeur.strip()
        for valeur in re.findall(r"^License:\s*(.+)$", texte, re.MULTILINE)
        if valeur.strip()
    }
    if not licences:
        licences = {f"référencée:{nom}" for nom in _REFERENCE_LICENCE.findall(texte)}
    return sorted(licences)


def manifeste_licences(image: str, binaires: list[dict]) -> list[dict]:
    """Relève, pour chaque paquet, son copyright et les textes référencés."""
    presents = set(_dans_image(image, f"ls {_COMMON} 2>/dev/null || true").split())
    entrees: list[dict] = []
    for paquet in binaires:
        nom = paquet["binary_package"]
        chemin = f"/usr/share/doc/{nom}/copyright"
        texte = _dans_image(image, f"cat {chemin} 2>/dev/null || true")
        licences = _licence_du_copyright(texte) if texte else []
        copyleft = [lic for lic in licences if any(f in lic.upper() for f in _COPYLEFT)]
        referencees = _REFERENCE_LICENCE.findall(texte)
        manquants = sorted({r for r in referencees if r not in presents})
        entrees.append(
            {
                "binary_package": nom,
                "version": paquet["version"],
                "copyright_file": chemin if texte else None,
                "copyright_present_in_image": bool(texte),
                "licenses_declared": licences,
                "copyleft_licenses": copyleft,
                "license_texts_referenced": sorted(set(referencees)),
                "referenced_texts_missing_from_image": manquants,
                "source_offer_obligation": bool(copyleft),
            }
        )
    return entrees


def paquets_sources(binaires: list[dict], manifeste: list[dict]) -> list[dict]:
    """Regroupe par paquet source, avec l'URL de snapshot correspondante."""
    par_licence = {entree["binary_package"]: entree for entree in manifeste}
    groupes: dict[tuple[str, str], dict] = {}
    for paquet in binaires:
        cle = (paquet["source_package"], paquet["source_version"])
        groupe = groupes.setdefault(
            cle,
            {
                "source_package": cle[0],
                "source_version": cle[1],
                "produces_binaries": [],
                "copyleft_licenses": set(),
                "source_offer_obligation": False,
                # Le snapshot est une archive immuable et datée : une version
                # retirée des miroirs courants y reste récupérable, ce qui est
                # exactement ce qu'exige une offre de source dans la durée.
                "snapshot_source_url": f"{SNAPSHOT}/package/{cle[0]}/{cle[1]}/",
                "source_availability": "à vérifier",
            },
        )
        groupe["produces_binaries"].append(paquet["binary_package"])
        info = par_licence.get(paquet["binary_package"], {})
        groupe["copyleft_licenses"].update(info.get("copyleft_licenses", []))
        groupe["source_offer_obligation"] |= bool(info.get("source_offer_obligation"))

    resultat = []
    for groupe in groupes.values():
        groupe["produces_binaries"] = sorted(groupe["produces_binaries"])
        groupe["copyleft_licenses"] = sorted(groupe["copyleft_licenses"])
        resultat.append(groupe)
    return sorted(resultat, key=lambda groupe: groupe["source_package"])


def verifier_disponibilite(sources: list[dict], delai: float = 15.0) -> None:
    """Interroge le snapshot pour chaque paquet source, et inscrit le constat.

    Une URL ecrite dans un manifeste ne prouve rien tant que personne ne l'a
    ouverte. Le champ ``source_availability`` passe donc de « a verifier » a un
    constat date, ou a l'erreur rencontree.
    """
    for groupe in sources:
        requete = urllib.request.Request(groupe["snapshot_source_url"], method="HEAD")
        try:
            with urllib.request.urlopen(requete, timeout=delai) as reponse:
                groupe["source_availability"] = f"verifie:HTTP {reponse.status}"
        except urllib.error.HTTPError as erreur:
            groupe["source_availability"] = f"indisponible:HTTP {erreur.code}"
        except OSError as erreur:  # reseau, DNS, TLS
            groupe["source_availability"] = f"non verifie:{type(erreur).__name__}"


def _defauts_qualifies(chemin: Path) -> set[tuple[str, str]]:
    """Couples (paquet, reference) dont le defaut de notice est deja motive."""
    if not chemin.is_file():
        return set()
    registre = json.loads(chemin.read_text(encoding="utf-8"))
    return {
        (entree["binary_package"], entree["missing_reference"])
        for entree in registre.get("exceptions", [])
    }


def _ecrire(chemin: Path, donnees: object) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(donnees, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="image RÉELLEMENT construite, pas un tag théorique")
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=Path("docs/governance/DEBIAN_NOTICE_EXCEPTIONS.json"),
        help="registre des defauts de notice deja qualifies par ecrit",
    )
    parser.add_argument(
        "--check-availability",
        action="store_true",
        help="interroge snapshot.debian.org pour chaque paquet source",
    )
    args = parser.parse_args(argv)

    binaires = paquets_binaires(args.image)
    manifeste = manifeste_licences(args.image, binaires)
    sources = paquets_sources(binaires, manifeste)

    if args.check_availability:
        verifier_disponibilite(sources)

    _ecrire(args.out / "debian-binary-packages.json", binaires)
    _ecrire(args.out / "debian-source-packages.json", sources)
    _ecrire(args.out / "debian-license-manifest.json", manifeste)

    # Un defaut de notice deja qualifie par ecrit n'est plus un defaut ouvert :
    # il reste visible dans le manifeste, mais ne bloque plus.
    qualifies = _defauts_qualifies(args.exceptions)

    sous_obligation = [e for e in manifeste if e["source_offer_obligation"]]
    sans_copyright = [e for e in manifeste if not e["copyright_present_in_image"]]
    textes_manquants = []
    for entree in manifeste:
        ouverts = [
            reference
            for reference in entree["referenced_texts_missing_from_image"]
            if (entree["binary_package"], reference) not in qualifies
        ]
        if ouverts:
            textes_manquants.append({**entree, "referenced_texts_missing_from_image": ouverts})

    print(f"Paquets binaires Debian        : {len(binaires)}")
    print(f"Paquets sources correspondants : {len(sources)}")
    print(f"Sous obligation de source      : {len(sous_obligation)}")
    print(f"Sans fichier copyright         : {len(sans_copyright)}")
    print(f"Textes de licence manquants    : {len(textes_manquants)} (non qualifies)")
    print(f"Defauts de notice qualifies    : {len(qualifies)} — {args.exceptions}")
    if args.check_availability:
        verifies = sum(1 for g in sources if g["source_availability"].startswith("verifie:"))
        indisponibles = [g for g in sources if g["source_availability"].startswith("indisponible:")]
        print(f"Sources verifiees au snapshot  : {verifies}/{len(sources)}")
        for groupe in indisponibles:
            print(f"  ! source introuvable : {groupe['source_package']} {groupe['source_version']}")

    for entree in sans_copyright:
        print(f"  ! copyright absent : {entree['binary_package']}")
    for entree in textes_manquants:
        print(
            f"  ! texte referencé absent : {entree['binary_package']} -> "
            f"{entree['referenced_texts_missing_from_image']}"
        )

    print(
        "\nCe manifeste est un CONSTAT, pas une conclusion juridique. "
        "L'offre de source reste à instruire : voir docs/compliance/SOURCE_COMPLIANCE.md."
    )

    # L'absence d'un fichier copyright ou d'un texte référencé est un défaut de
    # NOTICE, constatable sans avis juridique — c'est donc bloquant ici.
    if sans_copyright or textes_manquants:
        print("\nECHEC : la notice n'est pas complète dans l'image livrée.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

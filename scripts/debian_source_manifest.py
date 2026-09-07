"""Manifeste des paquets Debian de l'image, et de leurs sources correspondantes.

Distribuer une image, c'est distribuer les binaires qu'elle contient. Quand
certains sont sous une licence copyleft, une obligation de mise à disposition
des sources peut s'y attacher. Y répondre suppose d'abord de savoir, précisément,
*quels* paquets, dans *quelle* version, viennent de *quels fichiers* sources.

Ce script lit l'image **réellement construite** — jamais un fichier de
configuration, jamais une supposition — via ``dpkg-query`` et les fichiers
``copyright`` que Debian installe dans ``/usr/share/doc``. Il résout ensuite
chaque paquet source jusqu'au **fichier**, avec son URL, sa taille et son
empreinte SHA-256, en interrogeant l'archive immuable ``snapshot.debian.org``.

Trois fichiers sont produits, tous sous un en-tête de provenance qui identifie
l'image, la base, la plateforme et le commit :

``debian-binary-packages.json``
    un paquet binaire par entrée : nom, version, architecture, paquet source.

``debian-source-packages.json``
    un paquet **source** par entrée, avec les binaires qu'il produit et les
    **fichiers sources exacts** (``.dsc``, ``.orig.tar.*``, ``.debian.tar.*``…),
    leurs URL, tailles, SHA-256 et disponibilité constatée.

``debian-license-manifest.json``
    par paquet : licences relevées, famille, présence du ``copyright``,
    présence des textes référencés.

**Ce script ne conclut rien juridiquement.** Il classe des licences en familles
pour signaler ce qui doit être examiné, et n'affirme jamais qu'une forme
particulière de mise à disposition est due : cela dépend de la licence exacte,
du mode de distribution et du droit applicable. ``written_offer_applicability``
vaut donc invariablement ``LEGAL_REVIEW_REQUIRED``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

#: Version du générateur. À incrémenter dès que la forme des manifestes change,
#: sans quoi deux manifestes de structures différentes seraient indiscernables.
VERSION_SCRIPT = "2.0.0"

#: Snapshot Debian : archive immuable et datée, contrairement aux miroirs
#: courants où une version disparaît dès qu'elle est remplacée.
SNAPSHOT = "https://snapshot.debian.org"

#: User-Agent explicite : l'archive doit pouvoir identifier ce trafic.
USER_AGENT = f"ruggylab-os-source-manifest/{VERSION_SCRIPT} (+compliance evidence)"

#: Répertoire des textes de licence référencés par les fichiers copyright.
_COMMON = "/usr/share/common-licenses"

#: Référence à un texte de licence dans un fichier copyright Debian.
#
# Le nom NE DOIT PAS se terminer par un point : les fichiers copyright écrivent
# « voir /usr/share/common-licenses/GPL-2. », et une expression trop gourmande
# capturerait le point final de la phrase. On lirait alors « GPL-2. », absent du
# répertoire, et le manifeste signalerait un texte manquant qui ne l'est pas.
_REFERENCE_LICENCE = re.compile(re.escape(_COMMON) + r"/([A-Za-z0-9+\-]+(?:\.[A-Za-z0-9+\-]+)*)")

#: Champs demandés à dpkg, séparés par des tabulations.
_CHAMPS_DPKG = (
    r"${Package}\t${Version}\t${Architecture}\t"
    r"${source:Package}\t${source:Version}\t${Installed-Size}\n"
)

#: Familles de licences. L'ordre compte : « LGPL » et « AGPL » contiennent
#: « GPL » et doivent donc être reconnues d'abord.
#
# Cette classification est un SIGNAL DE REVUE, pas une décision juridique. Deux
# familles copyleft n'imposent pas les mêmes obligations : la portée de la MPL
# est le fichier, celle de la GPL l'œuvre, celle de l'AGPL s'étend à l'usage en
# réseau. Les regrouper sous une même conclusion serait faux.
_FAMILLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AGPL", ("AGPL",)),
    ("LGPL", ("LGPL",)),
    ("GPL", ("GPL",)),
    ("MPL", ("MPL", "MOZILLA")),
    ("EPL", ("EPL", "ECLIPSE")),
    ("CDDL", ("CDDL",)),
    (
        "PERMISSIVE",
        ("MIT", "BSD", "APACHE", "ISC", "ZLIB", "X11", "EXPAT", "PUBLIC-DOMAIN", "CC0"),
    ),
)

#: Familles dont la présence appelle un examen de mise à disposition des sources.
_FAMILLES_COPYLEFT = frozenset({"AGPL", "LGPL", "GPL", "MPL", "EPL", "CDDL"})

#: Ce que l'automatisation n'a pas le droit de trancher.
REVUE_JURIDIQUE = "LEGAL_REVIEW_REQUIRED"


# ── provenance ──────────────────────────────────────────────────────────────


def _commande(argv: list[str], defaut: str = "") -> str:
    resultat = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return resultat.stdout.strip() if resultat.returncode == 0 else defaut


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


def base_du_dockerfile(racine: Path) -> tuple[str, str]:
    """Référence et digest de la base, lus dans le Dockerfile versionné."""
    texte = (racine / "Dockerfile").read_text(encoding="utf-8")
    references = {
        ligne.split()[1]
        for ligne in texte.splitlines()
        if ligne.startswith("FROM ") and "@sha256:" in ligne
    }
    if not references:
        return ("", "")
    if len(references) != 1:
        raise RuntimeError(f"étapes construites sur des bases différentes : {references}")
    reference = references.pop()
    return (reference, reference.split("@", 1)[1])


def provenance(image: str, racine: Path) -> dict:
    """En-tête d'identification, sans lequel un manifeste ne décrit rien.

    Un manifeste sans provenance est ininterprétable : on ignore de quelle
    image, de quelle plateforme et de quel commit il parle. Deux manifestes de
    plateformes différentes se ressembleraient, et l'un passerait pour l'autre.
    """
    reference_base, digest_base = base_du_dockerfile(racine)
    inspect = _commande(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{.Id}}\t{{.Os}}\t{{.Architecture}}",
        ]
    )
    morceaux = inspect.split("\t") if inspect else []
    image_id = morceaux[0] if morceaux else ""
    systeme = morceaux[1] if len(morceaux) > 1 else ""
    architecture = morceaux[2] if len(morceaux) > 2 else ""

    # L'OS VU DANS l'image, et non déduit du tag.
    distribution = ""
    for ligne in _dans_image(image, "cat /etc/os-release 2>/dev/null || true").splitlines():
        if ligne.startswith("PRETTY_NAME="):
            distribution = ligne.split("=", 1)[1].strip('"')

    return {
        "script_version": VERSION_SCRIPT,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _commande(["git", "rev-parse", "HEAD"], "inconnu"),
        "image_reference": image,
        "image_id": image_id,
        "base_image_reference": reference_base,
        "base_image_digest": digest_base,
        "platform": f"{systeme}/{architecture}" if systeme and architecture else "",
        "os": systeme,
        "architecture": architecture,
        "distribution": distribution,
        "_comment": (
            "Ce manifeste ne décrit QUE la plateforme ci-dessus. Une publication "
            "multiplateforme exige un manifeste par plateforme : les paquets et "
            "leurs versions diffèrent d'une architecture à l'autre."
        ),
    }


# ── vérification réseau ─────────────────────────────────────────────────────


def _requete(url: str, methode: str, delai: float):
    requete = urllib.request.Request(url, method=methode, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(requete, timeout=delai)  # noqa: S310 - URL construite ici


def _classer_erreur(motif: object) -> dict:
    """Distingue la cause d'un échec réseau : elles n'appellent pas la même action."""
    texte = str(motif)
    if isinstance(motif, socket.timeout) or "timed out" in texte.lower():
        return {"status": "timeout", "detail": texte[:120]}
    if isinstance(motif, socket.gaierror) or "name or service" in texte.lower():
        return {"status": "dns_error", "detail": texte[:120]}
    if isinstance(motif, ssl.SSLError) or "ssl" in texte.lower() or "certificate" in texte.lower():
        return {"status": "tls_error", "detail": texte[:120]}
    return {"status": "unverified", "detail": f"{type(motif).__name__}: {texte[:100]}"}


def verifier_url(url: str, tentatives: int = 3, delai: float = 20.0) -> dict:
    """Constate si une URL répond, avec plusieurs tentatives et un repli GET.

    Un 404 est un fait durable ; un timeout ou une limitation de débit est
    passager. Aucun des deux n'est acceptable comme preuve, mais ils n'appellent
    pas la même action — le premier demande de corriger la référence, le second
    de relancer.

    Statuts : ``verified``, ``unavailable``, ``timeout``, ``tls_error``,
    ``dns_error``, ``rate_limited``, ``unverified``.
    """
    dernier: dict = {"status": "unverified", "detail": "aucune tentative"}
    for essai in range(tentatives):
        if essai:
            # Attente progressive : marteler une archive limitée en débit ne
            # ferait qu'aggraver la limitation.
            time.sleep(2**essai)
        for methode in ("HEAD", "GET"):
            try:
                with _requete(url, methode, delai) as reponse:
                    return {
                        "status": "verified",
                        "http_status": reponse.status,
                        "method": methode,
                        "attempts": essai + 1,
                    }
            except urllib.error.HTTPError as erreur:
                if methode == "HEAD" and erreur.code in (403, 405, 501):
                    # HEAD refusé : ce n'est pas une absence, on retente en GET.
                    continue
                if erreur.code == 429:
                    dernier = {"status": "rate_limited", "http_status": 429}
                elif erreur.code == 404:
                    return {"status": "unavailable", "http_status": 404, "method": methode}
                else:
                    dernier = {
                        "status": "unavailable",
                        "http_status": erreur.code,
                        "method": methode,
                    }
                break
            except urllib.error.URLError as erreur:
                dernier = _classer_erreur(getattr(erreur, "reason", erreur))
                break
            except OSError as erreur:
                dernier = _classer_erreur(erreur)
                break
    dernier.setdefault("attempts", tentatives)
    return dernier


def _lire_json(url: str, delai: float = 30.0) -> dict | None:
    try:
        with _requete(url, "GET", delai) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _telecharger(url: str, delai: float = 30.0) -> bytes | None:
    try:
        with _requete(url, "GET", delai) as reponse:
            return reponse.read()
    except (urllib.error.URLError, OSError):
        return None


# ── résolution des fichiers sources ─────────────────────────────────────────


def empreintes_du_dsc(contenu: bytes) -> dict[str, tuple[str, int]]:
    """Empreintes SHA-256 déclarées par Debian dans le `.dsc`, par nom de fichier."""
    empreintes: dict[str, tuple[str, int]] = {}
    dans_bloc = False
    for ligne in contenu.decode("utf-8", errors="replace").splitlines():
        if ligne.startswith("Checksums-Sha256:"):
            dans_bloc = True
            continue
        if dans_bloc:
            if not ligne.startswith(" "):
                break
            morceaux = ligne.split()
            if len(morceaux) >= 3:
                empreintes[morceaux[2]] = (morceaux[0], int(morceaux[1]))
    return empreintes


def resoudre_fichiers_sources(paquet: str, version: str, verifier: bool) -> dict:
    """Fichiers sources exacts d'un paquet, avec URL, taille et SHA-256.

    Un code HTTP 200 sur la page d'un paquet ne prouve rien sur ses fichiers :
    la page peut exister sans que l'archive source soit récupérable. On descend
    donc jusqu'au fichier, et l'on relève les empreintes que **Debian** déclare
    dans le ``.dsc`` — jamais une valeur inventée.
    """
    encode = urllib.parse.quote(version, safe="")
    api = (
        f"{SNAPSHOT}/mr/package/{urllib.parse.quote(paquet, safe='')}/{encode}/srcfiles?fileinfo=1"
    )
    donnees = _lire_json(api)
    if not donnees or not donnees.get("fileinfo"):
        return {
            "source_files": [],
            "source_files_resolution": "unresolved",
            "source_files_detail": f"aucun fichier renvoyé par {api}",
        }

    entrees = [
        (sha1, infos[0]["name"], infos[0].get("size"))
        for sha1, infos in donnees["fileinfo"].items()
    ]
    # Le `.dsc` d'abord : il porte les empreintes officielles des autres fichiers.
    entrees.sort(key=lambda e: (not e[1].endswith(".dsc"), e[1]))

    fichiers: list[dict] = []
    empreintes_declarees: dict[str, tuple[str, int]] = {}
    for sha1, nom, taille in entrees:
        url = f"{SNAPSHOT}/file/{sha1}"
        entree: dict = {
            "name": nom,
            "url": url,
            "size": taille,
            "snapshot_sha1": sha1,
            "sha256": None,
            "sha256_source": None,
            "availability": "unverified",
        }
        if nom.endswith(".dsc") and verifier:
            contenu = _telecharger(url)
            if contenu is not None:
                # Le `.dsc` ne contient pas sa propre empreinte : la seule
                # honnête est celle du fichier qu'on vient de recevoir.
                entree["sha256"] = hashlib.sha256(contenu).hexdigest()
                entree["sha256_source"] = "computed_on_downloaded_file"
                entree["availability"] = "verified"
                empreintes_declarees = empreintes_du_dsc(contenu)
            else:
                entree["availability"] = "unavailable"
                entree["availability_detail"] = "téléchargement du .dsc impossible"
        fichiers.append(entree)

    for entree in fichiers:
        if entree["name"] in empreintes_declarees:
            sha256, taille = empreintes_declarees[entree["name"]]
            entree["sha256"] = sha256
            entree["sha256_source"] = "debian_dsc_checksums_sha256"
            if entree["size"] is None:
                entree["size"] = taille
        if verifier and entree["availability"] == "unverified":
            resultat = verifier_url(entree["url"])
            entree["availability"] = resultat.pop("status")
            entree.update({f"availability_{cle}": val for cle, val in resultat.items()})

    # Le `.dsc` est l'AUTORITÉ sur ce qui compose le source correspondant.
    # L'archive publie parfois, à côté, des fichiers qui n'en font pas partie —
    # ainsi de `<paquet>_<version>.git.tar.xz` pour les paquets gérés par dgit,
    # qui empaquette l'historique git et n'est référencé que par le champ
    # `Dgit:`, jamais par `Checksums-Sha256`. Les compter parmi les fichiers
    # sources produirait un « hash manquant » qui n'en est pas un ; les inventer
    # un hash serait pire. On les recense à part, avec le motif.
    attendus = set(empreintes_declarees)
    sources = [f for f in fichiers if f["name"].endswith(".dsc") or f["name"] in attendus]
    connexes = [f for f in fichiers if f not in sources]
    for fichier in connexes:
        fichier["excluded_reason"] = (
            "présent dans l'archive mais absent des Checksums-Sha256 du .dsc : "
            "ne fait pas partie du source correspondant déclaré par Debian"
        )

    return {
        "source_files": sources,
        "related_archive_files": connexes,
        "source_files_resolution": "resolved" if sources else "unresolved",
        "source_files_without_sha256": [f["name"] for f in sources if not f["sha256"]],
        "source_files_not_verified": (
            [f["name"] for f in sources if f["availability"] != "verified"]
            if verifier
            else ["(vérification non demandée)"]
        ),
    }


# ── inventaire ──────────────────────────────────────────────────────────────


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


def famille_de_licence(expression: str) -> str:
    """Famille d'une expression de licence. Classement, pas qualification.

    Renvoie ``UNKNOWN`` plutôt que de forcer une famille : une licence non
    reconnue doit être examinée, pas rangée par défaut du côté rassurant.
    """
    majuscules = expression.upper()
    for famille, motifs in _FAMILLES:
        if any(motif in majuscules for motif in motifs):
            return famille
    return "UNKNOWN"


def manifeste_licences(image: str, binaires: list[dict]) -> list[dict]:
    """Relève, pour chaque paquet, son copyright et les textes référencés."""
    presents = set(_dans_image(image, f"ls {_COMMON} 2>/dev/null || true").split())
    entrees: list[dict] = []
    for paquet in binaires:
        nom = paquet["binary_package"]
        chemin = f"/usr/share/doc/{nom}/copyright"
        texte = _dans_image(image, f"cat {chemin} 2>/dev/null || true")
        licences = _licence_du_copyright(texte) if texte else []
        familles = sorted({famille_de_licence(lic) for lic in licences})
        copyleft = sorted(f for f in familles if f in _FAMILLES_COPYLEFT)
        referencees = _REFERENCE_LICENCE.findall(texte)
        manquants = sorted({r for r in referencees if r not in presents})
        entrees.append(
            {
                "binary_package": nom,
                "version": paquet["version"],
                "copyright_file": chemin if texte else None,
                "copyright_present_in_image": bool(texte),
                "detected_license_expression": licences,
                "license_family": familles,
                "copyleft_detected": bool(copyleft),
                "copyleft_families": copyleft,
                # Un signal de revue, jamais une conclusion : la forme de mise à
                # disposition dépend de la licence exacte, du mode de
                # distribution et du droit applicable.
                "source_compliance_review_required": bool(copyleft),
                "written_offer_applicability": REVUE_JURIDIQUE,
                "license_texts_referenced": sorted(set(referencees)),
                "referenced_texts_missing_from_image": manquants,
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
                "copyleft_families": set(),
                "copyleft_detected": False,
                "source_compliance_review_required": False,
                "written_offer_applicability": REVUE_JURIDIQUE,
                # Le snapshot est une archive immuable et datée : une version
                # retirée des miroirs courants y reste récupérable, ce qui est
                # exactement ce qu'exige une mise à disposition dans la durée.
                "snapshot_package_url": f"{SNAPSHOT}/package/{cle[0]}/{cle[1]}/",
                "source_availability": "à vérifier",
                "source_files": [],
                "related_archive_files": [],
                "source_files_resolution": "not_attempted",
            },
        )
        groupe["produces_binaries"].append(paquet["binary_package"])
        info = par_licence.get(paquet["binary_package"], {})
        groupe["copyleft_families"].update(info.get("copyleft_families", []))
        groupe["copyleft_detected"] |= bool(info.get("copyleft_detected"))
        groupe["source_compliance_review_required"] |= bool(
            info.get("source_compliance_review_required")
        )

    resultat = []
    for groupe in groupes.values():
        groupe["produces_binaries"] = sorted(groupe["produces_binaries"])
        groupe["copyleft_families"] = sorted(groupe["copyleft_families"])
        resultat.append(groupe)
    return sorted(resultat, key=lambda groupe: groupe["source_package"])


def resoudre_sources(sources: list[dict], verifier: bool) -> None:
    """Descend chaque paquet source jusqu'à ses fichiers, et les vérifie."""
    for groupe in sources:
        if verifier:
            resultat = verifier_url(groupe["snapshot_package_url"])
            groupe["source_availability"] = resultat["status"]
            if resultat.get("http_status"):
                groupe["source_availability_http"] = resultat["http_status"]
        groupe.update(
            resoudre_fichiers_sources(groupe["source_package"], groupe["source_version"], verifier)
        )


def _defauts_qualifies(chemin: Path) -> set[tuple[str, str]]:
    """Couples (paquet, reference) dont le defaut de notice est deja motive."""
    if not chemin.is_file():
        return set()
    registre = json.loads(chemin.read_text(encoding="utf-8"))
    return {
        (entree["binary_package"], entree["missing_reference"])
        for entree in registre.get("exceptions", [])
    }


def _ecrire(chemin: Path, entete: dict, cle: str, donnees: object) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(
            {"provenance": entete, cle: donnees}, indent=2, ensure_ascii=False, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def _echecs_de_disponibilite(sources: list[dict]) -> list[str]:
    """Tout ce qui n'est pas `verified` bloque : une panne externe ne prouve rien."""
    echecs: list[str] = []
    for groupe in sources:
        if groupe["source_availability"] != "verified":
            echecs.append(
                f"paquet source non vérifié : {groupe['source_package']} "
                f"{groupe['source_version']} -> {groupe['source_availability']}"
            )
        if groupe["source_files_resolution"] != "resolved":
            echecs.append(
                f"fichiers sources non résolus : {groupe['source_package']} "
                f"-> {groupe.get('source_files_detail', '')}"
            )
        for fichier in groupe["source_files"]:
            if fichier["availability"] != "verified":
                echecs.append(
                    f"fichier source non vérifié : {fichier['name']} -> {fichier['availability']}"
                )
            if not fichier.get("sha256"):
                echecs.append(f"fichier source sans SHA-256 : {fichier['name']}")
    return echecs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="image RÉELLEMENT construite, pas un tag théorique")
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=Path("docs/governance/DEBIAN_NOTICE_EXCEPTIONS.json"),
        help="registre des defauts de notice deja qualifies par ecrit",
    )
    parser.add_argument(
        "--check-availability",
        action="store_true",
        help="résout et vérifie les fichiers sources sur snapshot.debian.org",
    )
    args = parser.parse_args(argv)

    entete = provenance(args.image, args.root)
    binaires = paquets_binaires(args.image)
    manifeste = manifeste_licences(args.image, binaires)
    sources = paquets_sources(binaires, manifeste)
    resoudre_sources(sources, args.check_availability)

    _ecrire(args.out / "debian-binary-packages.json", entete, "binary_packages", binaires)
    _ecrire(args.out / "debian-source-packages.json", entete, "source_packages", sources)
    _ecrire(args.out / "debian-license-manifest.json", entete, "license_manifest", manifeste)

    qualifies = _defauts_qualifies(args.exceptions)
    a_revoir = [e for e in manifeste if e["source_compliance_review_required"]]
    sans_copyright = [e for e in manifeste if not e["copyright_present_in_image"]]
    textes_manquants = [
        (e["binary_package"], ouverts)
        for e in manifeste
        if (
            ouverts := [
                reference
                for reference in e["referenced_texts_missing_from_image"]
                if (e["binary_package"], reference) not in qualifies
            ]
        )
    ]

    print(f"Plateforme                     : {entete['platform']} — {entete['distribution']}")
    print(f"Base                           : {entete['base_image_reference']}")
    print(f"Commit                         : {entete['git_sha'][:12]}")
    print(f"Paquets binaires Debian        : {len(binaires)}")
    print(f"Paquets sources correspondants : {len(sources)}")
    print(f"Copyleft détecté (à examiner)  : {len(a_revoir)} paquet(s)")
    print(f"Sans fichier copyright         : {len(sans_copyright)}")
    print(f"Textes de licence manquants    : {len(textes_manquants)} (non qualifiés)")
    print(f"Défauts de notice qualifiés    : {len(qualifies)} — {args.exceptions}")

    echecs = [f"copyright absent : {e['binary_package']}" for e in sans_copyright]
    echecs += [f"texte référencé absent : {nom} -> {refs}" for nom, refs in textes_manquants]

    if args.check_availability:
        verifies = sum(1 for g in sources if g["source_availability"] == "verified")
        fichiers = [f for g in sources for f in g["source_files"]]
        fichiers_ok = sum(1 for f in fichiers if f["availability"] == "verified")
        sans_hash = sum(1 for f in fichiers if not f.get("sha256"))
        print(f"Paquets sources vérifiés       : {verifies}/{len(sources)}")
        print(f"Fichiers sources résolus       : {len(fichiers)}")
        print(f"Fichiers sources vérifiés      : {fichiers_ok}/{len(fichiers)}")
        print(f"Fichiers sans SHA-256          : {sans_hash}")
        echecs += _echecs_de_disponibilite(sources)

    print(
        "\nCe manifeste est un CONSTAT, pas une conclusion juridique. La forme de "
        "mise à disposition des sources reste à instruire : voir "
        "docs/compliance/SOURCE_COMPLIANCE.md."
    )

    if echecs:
        print(f"\nECHEC : {len(echecs)} point(s) bloquant(s).", file=sys.stderr)
        for message in echecs[:40]:
            print(f"  ! {message}", file=sys.stderr)
        if len(echecs) > 40:
            print(f"  … et {len(echecs) - 40} autre(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

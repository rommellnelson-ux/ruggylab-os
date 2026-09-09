"""Résumé structuré de la couverture G0 (preuve 7) — et contrôle de sa validité.

Ce script ne mesure rien. Il **lit** ce que `coverage` a produit — le rapport
XML et le rapport JSON — et en dérive un résumé exploitable dans une revue :
totaux, regroupements, dix plus gros volumes non couverts, modules jamais
importés.

Pourquoi deux formats en entrée plutôt qu'un seul ? Parce qu'ils se contrôlent
mutuellement. Le JSON de `coverage` porte le détail par fichier et le drapeau
`meta.branch_coverage` ; le XML porte les totaux agrégés sous une autre forme.
Un résumé dérivé d'une seule source ne pourrait pas être contredit : si le
générateur se trompait, personne ne le saurait. Ici les deux doivent concorder,
et `--check` refuse la divergence.

Aucun seuil n'est inscrit ici, et il ne faut pas en ajouter. G0 **constate**.
Un seuil transformerait la mesure en verdict, et un verdict se contourne en
choisissant les tests. Le chiffre est publié tel qu'il sort, faible ou non.

Ce que ce module refuse — chaque refus correspond à une mutation rejouée :

``--cov-branch`` absent
    Un rapport lignes seules porte `branch_coverage: false` et aucun attribut
    `condition-coverage`. Il serait indiscernable d'un rapport de branches à
    100 % si l'on ne regardait que les pourcentages.

Périmètre réduit
    Mesurer `--cov=app.api` produit un rapport parfaitement valide, dont le
    pourcentage est flatteur parce qu'il ignore le reste. Le contrôle compare
    donc les fichiers rapportés à l'arborescence réelle de ``app/`` et refuse
    toute absence.

XML incomplet
    Un fichier tronqué ne se parse pas, ou se parse sans totaux. Les deux cas
    sont des échecs.

Regroupement critique manquant
    Les regroupements listés dans ``REGROUPEMENTS`` doivent tous exister et
    porter au moins une instruction.

Aucun appel réseau. Aucun secret. Aucune donnée patient.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - lecture d'un XML produit localement
from pathlib import Path
from typing import Any

#: Structure du résumé. À incrémenter dès que sa forme change.
SCHEMA_VERSION = "1.0.0"

#: Version du générateur. Un changement de résultat s'explique d'abord par là.
GENERATOR_VERSION = "1.0.0"

RACINE = Path(__file__).resolve().parents[1]

if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Regroupements exigés par la campagne. Chacun est un préfixe de chemin POSIX.
#: Leur absence est un échec : un résumé qui ometterait `app/services/csa_sync`
#: laisserait croire que l'intégration CSA a été mesurée alors qu'elle ne
#: l'aurait pas été.
REGROUPEMENTS: tuple[str, ...] = (
    "app/api",
    "app/core",
    "app/services",
    "app/services/validation",
    "app/services/interfacing",
    "app/services/csa_sync",
    "app/models",
    "app/utils",
)

#: Modules cliniques critiques — ceux dont un défaut se traduit par un résultat
#: faux rendu à un patient, ou par une valeur critique non signalée. Ils sont
#: suivis nommément parce qu'un pourcentage global les noie : 90 % de couverture
#: globale est compatible avec 0 % sur la vérification des valeurs critiques.
MODULES_CLINIQUES_CRITIQUES: tuple[str, ...] = (
    "app/services/critical_checker.py",
    "app/services/critical_notifier.py",
    "app/services/auto_validator.py",
    "app/services/delta_checker.py",
    "app/services/reference_checker.py",
    "app/services/preanalytic.py",
    "app/services/result_service.py",
    "app/services/validation/med_logic.py",
    "app/services/validation/precis_expert.py",
    "app/services/validation/poct_reference.py",
    "app/services/exam_order_service.py",
    "app/services/malaria_ai.py",
)


def _normaliser(chemin: str) -> str:
    """Le chemin d'un fichier tel qu'il entre dans le résumé.

    `coverage` écrit des séparateurs Windows sous Windows et POSIX sous Linux.
    Sans normalisation, le même code produirait deux résumés incomparables
    selon la machine de mesure.
    """
    return chemin.replace("\\", "/").lstrip("./")


def fichiers_application() -> list[str]:
    """Les modules Python de ``app/`` réellement présents sur le disque.

    Sert de référence au contrôle de périmètre : le rapport de couverture doit
    tous les mentionner, sinon la mesure porte sur un sous-ensemble choisi.
    """
    racine_app = RACINE / "app"
    trouves = [
        _normaliser(str(chemin.relative_to(RACINE).as_posix()))
        for chemin in racine_app.rglob("*.py")
        if "__pycache__" not in chemin.parts
    ]
    return sorted(trouves)


def charger_json(chemin: Path) -> dict[str, Any]:
    """Le rapport JSON de `coverage`, refusé s'il n'est pas un rapport."""
    donnees: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    if "files" not in donnees or "totals" not in donnees:
        raise ValueError(f"{chemin.name} : ce n'est pas un rapport coverage JSON")
    return donnees


def _attribut_flottant(element: ET.Element, nom: str) -> float | None:
    valeur = element.get(nom)
    if valeur is None:
        return None
    try:
        return float(valeur)
    except ValueError:
        return None


def _attribut_entier(element: ET.Element, nom: str) -> int | None:
    valeur = element.get(nom)
    if valeur is None:
        return None
    try:
        return int(valeur)
    except ValueError:
        return None


def lire_xml(chemin: Path) -> dict[str, Any]:
    """Les totaux du XML Cobertura, et la preuve que les branches y figurent.

    `condition_coverage_attributs` est le point important : `coverage`
    n'émet `condition-coverage="…"` sur les lignes que lorsque la mesure des
    branches est active. Les attributs `branch-rate` existent dans les deux cas
    — à 0 quand les branches ne sont pas mesurées — et ne suffisent donc pas à
    prouver quoi que ce soit.
    """
    arbre = ET.parse(chemin)  # noqa: S314 - fichier produit localement par coverage
    racine = arbre.getroot()
    if racine.tag != "coverage":
        raise ValueError(f"{chemin.name} : racine <{racine.tag}>, attendu <coverage>")
    conditions = sum(1 for ligne in racine.iter("line") if ligne.get("condition-coverage"))
    paquets = [p.get("name", "") for p in racine.iter("package")]
    classes = [_normaliser(c.get("filename", "")) for c in racine.iter("class")]
    return {
        "line_rate": _attribut_flottant(racine, "line-rate"),
        "branch_rate": _attribut_flottant(racine, "branch-rate"),
        "lines_covered": _attribut_entier(racine, "lines-covered"),
        "lines_valid": _attribut_entier(racine, "lines-valid"),
        "branches_covered": _attribut_entier(racine, "branches-covered"),
        "branches_valid": _attribut_entier(racine, "branches-valid"),
        "condition_coverage_attributs": conditions,
        "packages": sorted(set(paquets)),
        "files": sorted(set(classes)),
    }


def _pourcentage(couvert: int, total: int) -> float:
    """Un pourcentage, arrondi au centième. Zéro instruction n'est pas 100 %."""
    if total <= 0:
        return 0.0
    return round(100.0 * couvert / total, 2)


def _agreger(entrees: list[dict[str, Any]]) -> dict[str, Any]:
    lignes = sum(e["statements"] for e in entrees)
    couvertes = sum(e["covered_statements"] for e in entrees)
    branches = sum(e["branches"] for e in entrees)
    branches_couvertes = sum(e["covered_branches"] for e in entrees)
    return {
        "modules": len(entrees),
        "statements": lignes,
        "covered_statements": couvertes,
        "missing_statements": lignes - couvertes,
        "line_percent": _pourcentage(couvertes, lignes),
        "branches": branches,
        "covered_branches": branches_couvertes,
        "missing_branches": branches - branches_couvertes,
        "branch_percent": _pourcentage(branches_couvertes, branches),
    }


def construire(rapport_json: dict[str, Any], rapport_xml: dict[str, Any]) -> dict[str, Any]:
    """Le résumé, dérivé du rapport JSON et croisé avec le XML."""
    modules: list[dict[str, Any]] = []
    for chemin_brut, donnees in rapport_json["files"].items():
        resume = donnees["summary"]
        chemin = _normaliser(chemin_brut)
        couvertes = int(resume["covered_lines"])
        instructions = int(resume["num_statements"])
        branches = int(resume.get("num_branches", 0))
        branches_couvertes = int(resume.get("covered_branches", 0))
        modules.append(
            {
                "module": chemin,
                "statements": instructions,
                "covered_statements": couvertes,
                "missing_statements": instructions - couvertes,
                "line_percent": _pourcentage(couvertes, instructions),
                "branches": branches,
                "covered_branches": branches_couvertes,
                "partial_branches": int(resume.get("num_partial_branches", 0)),
                "missing_branches": branches - branches_couvertes,
                "branch_percent": _pourcentage(branches_couvertes, branches),
                "excluded_lines": int(resume.get("excluded_lines", 0)),
                "executed": couvertes > 0,
            }
        )
    modules.sort(key=lambda m: m["module"])

    totaux_json = rapport_json["totals"]
    totaux = {
        "statements": int(totaux_json["num_statements"]),
        "covered_statements": int(totaux_json["covered_lines"]),
        "missing_statements": int(totaux_json["missing_lines"]),
        "line_percent": _pourcentage(
            int(totaux_json["covered_lines"]), int(totaux_json["num_statements"])
        ),
        "branches": int(totaux_json.get("num_branches", 0)),
        "covered_branches": int(totaux_json.get("covered_branches", 0)),
        "partial_branches": int(totaux_json.get("num_partial_branches", 0)),
        "missing_branches": int(totaux_json.get("missing_branches", 0)),
        "branch_percent": _pourcentage(
            int(totaux_json.get("covered_branches", 0)), int(totaux_json.get("num_branches", 0))
        ),
        "excluded_lines": int(totaux_json.get("excluded_lines", 0)),
        "measured_modules": len(modules),
    }

    # Un regroupement est un préfixe : `app/services` contient
    # `app/services/csa_sync`. Les deux sont publiés — l'imbrication est
    # explicite, et vouloir des ensembles disjoints donnerait des chiffres que
    # personne ne saurait recomposer.
    regroupements: dict[str, Any] = {}
    for prefixe in REGROUPEMENTS:
        membres = [m for m in modules if m["module"].startswith(prefixe + "/")]
        regroupements[prefixe] = _agreger(membres)

    critiques = {
        nom: next(
            (m for m in modules if m["module"] == nom),
            {"module": nom, "present_in_report": False},
        )
        for nom in MODULES_CLINIQUES_CRITIQUES
    }

    plus_gros_trous = sorted(modules, key=lambda m: (-m["missing_statements"], m["module"]))[:10]

    jamais_importes = [m["module"] for m in modules if not m["executed"] and m["statements"] > 0]

    from scripts.g0_provenance import provenance

    return {
        "schema_version": SCHEMA_VERSION,
        "payload": {
            "_comment": (
                "Constat, pas verdict. Aucun seuil n'est inscrit ici et il ne faut "
                "pas en ajouter : un seuil se contourne en choisissant les tests."
            ),
            "measurement": {
                "coverage_version": rapport_json.get("meta", {}).get("version"),
                "branch_coverage": bool(rapport_json.get("meta", {}).get("branch_coverage")),
                "coverage_report_timestamp": rapport_json.get("meta", {}).get("timestamp"),
                "generator_version": GENERATOR_VERSION,
            },
            "totals": totaux,
            "xml_cross_check": rapport_xml,
            "by_package": regroupements,
            "clinical_critical_modules": critiques,
            "top_10_uncovered_by_statements": [
                {
                    "module": m["module"],
                    "missing_statements": m["missing_statements"],
                    "statements": m["statements"],
                    "line_percent": m["line_percent"],
                    "branch_percent": m["branch_percent"],
                }
                for m in plus_gros_trous
            ],
            "never_executed_modules": jamais_importes,
            "never_executed_module_count": len(jamais_importes),
            "by_module": modules,
        },
        "provenance": provenance(
            "coverage",
            "python scripts/g0_coverage_summary.py --generate",
            schema_version=SCHEMA_VERSION,
            generator_version=GENERATOR_VERSION,
        ),
    }


def controler(resume: dict[str, Any]) -> list[str]:
    """Les écarts qui invalident une mesure de couverture. Vide si tout tient.

    Chaque entrée correspond à une mutation qui doit être détectée (§22). Un
    contrôle qui passerait sur ces mutations serait aveugle, et le chiffre
    qu'il accompagne n'aurait aucune valeur de preuve.
    """
    ecarts: list[str] = []
    corps = resume.get("payload")
    if not isinstance(corps, dict):
        return ["resume : bloc `payload` absent"]

    mesure = corps.get("measurement", {})
    xml = corps.get("xml_cross_check", {})
    totaux = corps.get("totals", {})

    # 1. Les branches sont-elles réellement mesurées ?
    if not mesure.get("branch_coverage"):
        ecarts.append(
            "branches non mesurees : le rapport porte branch_coverage=false "
            "(--cov-branch absent de la commande)"
        )
    if not xml.get("condition_coverage_attributs"):
        ecarts.append(
            "XML sans attribut condition-coverage : mesure lignes seules, "
            "indiscernable d'un rapport de branches sans les branches"
        )

    # 2. Le XML est-il complet ?
    for cle in ("lines_valid", "lines_covered", "branches_valid", "branches_covered"):
        if xml.get(cle) is None:
            ecarts.append(f"XML incomplet : totaux `{cle}` absents")
    if not xml.get("packages"):
        ecarts.append("XML incomplet : aucun <package>")
    if (xml.get("lines_valid") or 0) <= 0:
        ecarts.append("XML incomplet : lines-valid nul ou absent")

    # 3. Les deux sources concordent-elles ?
    if xml.get("lines_valid") is not None and xml["lines_valid"] != totaux.get("statements"):
        ecarts.append(
            f"incoherence XML/JSON : lines-valid={xml['lines_valid']} "
            f"contre statements={totaux.get('statements')}"
        )
    if xml.get("lines_covered") is not None and xml["lines_covered"] != totaux.get(
        "covered_statements"
    ):
        ecarts.append(
            f"incoherence XML/JSON : lines-covered={xml['lines_covered']} "
            f"contre covered_statements={totaux.get('covered_statements')}"
        )
    if xml.get("branches_valid") is not None and xml["branches_valid"] != totaux.get("branches"):
        ecarts.append(
            f"incoherence XML/JSON : branches-valid={xml['branches_valid']} "
            f"contre branches={totaux.get('branches')}"
        )

    # 4. Le périmètre couvre-t-il toute l'application ?
    rapportes = {m["module"] for m in corps.get("by_module", [])}
    manquants = [chemin for chemin in fichiers_application() if chemin not in rapportes]
    if manquants:
        apercu = ", ".join(manquants[:5])
        ecarts.append(
            f"perimetre reduit : {len(manquants)} module(s) de app/ absents du "
            f"rapport (ex. {apercu})"
        )

    # 5. Tous les regroupements exigés sont-ils présents et non vides ?
    paquets = corps.get("by_package", {})
    for prefixe in REGROUPEMENTS:
        if prefixe not in paquets:
            ecarts.append(f"regroupement `{prefixe}` absent du resume")
        elif (paquets[prefixe] or {}).get("statements", 0) <= 0:
            ecarts.append(f"regroupement `{prefixe}` sans aucune instruction mesuree")

    return ecarts


def _ecrire(chemin: Path, contenu: dict[str, Any]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(contenu, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, default=RACINE / "artifacts" / "g0" / "coverage.xml")
    parser.add_argument("--json", type=Path, default=RACINE / "artifacts" / "g0" / "coverage.json")
    parser.add_argument(
        "--output", type=Path, default=RACINE / "artifacts" / "g0" / "coverage-summary.json"
    )
    parser.add_argument("--generate", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="controle la validite du resume deja ecrit (mutations du §22)",
    )
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    if not (args.generate or args.check or args.print_summary):
        parser.error("choisir --generate, --check ou --print-summary")

    if args.check and not args.generate:
        try:
            resume = json.loads(args.output.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"ECHEC : {args.output} absent", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"ECHEC : {args.output} illisible ({exc})", file=sys.stderr)
            return 1
    else:
        try:
            rapport_json = charger_json(args.json)
            rapport_xml = lire_xml(args.xml)
        except (OSError, ValueError, ET.ParseError) as exc:
            print(f"ECHEC : rapport de couverture inexploitable — {exc}", file=sys.stderr)
            return 1
        resume = construire(rapport_json, rapport_xml)

    if args.print_summary:
        corps = resume["payload"]
        t = corps["totals"]
        print(f"Instructions       : {t['covered_statements']}/{t['statements']}")
        print(f"  couverture lignes: {t['line_percent']} %")
        print(f"Branches           : {t['covered_branches']}/{t['branches']}")
        print(f"  couverture branch: {t['branch_percent']} %")
        print(f"Modules mesures    : {t['measured_modules']}")
        print(f"Modules jamais executes : {corps['never_executed_module_count']}")
        print("\nPar regroupement :")
        for nom, valeurs in corps["by_package"].items():
            print(
                f"  {nom:32s} lignes {valeurs['line_percent']:6.2f} %  "
                f"branches {valeurs['branch_percent']:6.2f} %  "
                f"({valeurs['covered_statements']}/{valeurs['statements']})"
            )

    if args.generate:
        _ecrire(args.output, resume)
        print(f"Resume ecrit dans {args.output}")

    if args.check:
        ecarts = controler(resume)
        if ecarts:
            print("\nECHEC : la mesure de couverture est invalide.", file=sys.stderr)
            for ligne in ecarts:
                print(f"  ! {ligne}", file=sys.stderr)
            return 1
        print("\nMesure de couverture : valide (branches mesurees, perimetre complet).")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

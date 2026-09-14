"""Décompte des jobs de CI d'une révision — mesuré, jamais saisi à la main.

POURQUOI CE SCRIPT EXISTE
-------------------------
Le corps de la PR #150 annonçait « 16 SUCCESS / 2 SKIPPED ». Le relevé
indépendant a trouvé **15 SUCCESS / 2 SKIPPED**. Ni l'un ni l'autre n'était une
faute de frappe : le 16 venait de ``gh pr view --json statusCheckRollup``, qui
agrège les *check runs* d'une tête — et CodeQL en publie un en plus des jobs du
workflow. Le rollup comptait donc :

    13 jobs du workflow CI
  +  2 jobs du workflow qualité
  +  1 check run « CodeQL » posé par l'action elle-même
  = 16

Le nombre était exact pour ce qu'il comptait, et faux pour ce qu'il prétendait
décrire. C'est la forme la plus tenace d'erreur de preuve : un chiffre juste,
mal étiqueté.

Ce script compte des **jobs**, workflow par workflow, depuis l'API GitHub, et
publie la distinction explicitement. Aucun décompte n'a plus à être recopié.

Aucun secret, aucune donnée patient. Lecture seule.

Usage :
    python scripts/g0_ci_job_report.py --sha <SHA> [--markdown]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from typing import Any

DEPOT = "rommellnelson-ux/ruggylab-os"


def _gh(*arguments: str) -> Any:
    """Un appel `gh api`, sans shell. Lève si la commande échoue."""
    binaire = shutil.which("gh")
    if binaire is None:
        raise RuntimeError("gh introuvable")
    acheve = subprocess.run(  # noqa: S603 - arguments litteraux, jamais de shell
        [binaire, *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if acheve.returncode != 0:
        raise RuntimeError(f"gh {' '.join(arguments)} : {acheve.stderr.strip()}")
    return json.loads(acheve.stdout)


def executions(sha: str, depot: str) -> list[dict[str, Any]]:
    """Les exécutions de workflow portant exactement sur cette révision."""
    charge = _gh("api", f"repos/{depot}/actions/runs?head_sha={sha}&per_page=100")
    return [r for r in charge.get("workflow_runs", []) if r.get("head_sha") == sha]


def jobs(run_id: int, depot: str) -> list[dict[str, Any]]:
    charge = _gh("api", f"repos/{depot}/actions/runs/{run_id}/jobs?per_page=100")
    return list(charge.get("jobs", []))


def rapport(sha: str, depot: str = DEPOT) -> dict[str, Any]:
    """Le décompte, par workflow puis au total. Des JOBS, pas des check runs."""
    par_workflow: list[dict[str, Any]] = []
    total: Counter[str] = Counter()
    for execution in sorted(executions(sha, depot), key=lambda r: r["name"]):
        verdicts = Counter(
            str(j.get("conclusion") or "en_cours") for j in jobs(execution["id"], depot)
        )
        total.update(verdicts)
        par_workflow.append(
            {
                "workflow": execution["name"],
                "run_id": execution["id"],
                "run_attempt": execution.get("run_attempt"),
                "conclusion": execution.get("conclusion"),
                "jobs": dict(sorted(verdicts.items())),
                "job_count": sum(verdicts.values()),
            }
        )
    return {
        "head_sha": sha,
        "repository": depot,
        "workflows": par_workflow,
        "totals": dict(sorted(total.items())),
        "job_total": sum(total.values()),
        "_comment": (
            "Ce decompte porte sur des JOBS. `gh pr view --json statusCheckRollup` "
            "compte en plus les check runs poses par certaines actions (CodeQL en "
            "publie un), et rend donc un nombre superieur qui ne decrit pas les jobs."
        ),
    }


def en_markdown(donnees: dict[str, Any]) -> str:
    lignes = [
        f"Décompte des **jobs** sur `{donnees['head_sha'][:7]}` (des jobs, pas des check runs) :",
        "",
        "| Workflow | Jobs | Détail |",
        "| --- | ---: | --- |",
    ]
    for w in donnees["workflows"]:
        detail = " · ".join(f"{n} {v}" for v, n in w["jobs"].items())
        lignes.append(f"| {w['workflow']} (run `{w['run_id']}`) | {w['job_count']} | {detail} |")
    total = " · ".join(f"**{n} {v.upper()}**" for v, n in donnees["totals"].items())
    lignes += ["", f"**Total : {donnees['job_total']} jobs** — {total}"]
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="revision exacte a compter")
    parser.add_argument("--repo", default=DEPOT)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)

    try:
        donnees = rapport(args.sha, args.repo)
    except (RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"ECHEC : {exc}", file=sys.stderr)
        return 1

    if args.markdown:
        print(en_markdown(donnees))
    else:
        print(json.dumps(donnees, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

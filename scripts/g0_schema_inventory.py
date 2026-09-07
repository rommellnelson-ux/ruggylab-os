"""Inventaire G0 — schéma PostgreSQL réellement créé, et graphe Alembic.

**Introspection d'une base migrée, jamais lecture des modèles Python.** Les
deux peuvent diverger : une migration écrite à la main, un `server_default`
oublié, un index créé hors modèle. Décrire les modèles reviendrait à décrire ce
qu'on croit avoir, pas ce qu'on a.

Deux artefacts :

``schema.json``
    schémas, tables, colonnes, types, nullabilité, valeurs par défaut, clés
    primaires et étrangères, contraintes UNIQUE et CHECK, index, vues,
    séquences, enums, fonctions, triggers, extensions et politiques RLS.

``alembic-graph.json``
    toutes les révisions, leurs parents, les branches, les fusions, l'ordre
    topologique et le nombre de têtes.

Usage :

    python scripts/g0_schema_inventory.py --database-url postgresql+psycopg://... --generate

La base doit avoir reçu ``alembic upgrade head`` au préalable. Le script ne la
migre pas lui-même : migrer et introspecter dans le même processus masquerait
une migration qui échoue partiellement.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"
RACINE = Path(__file__).resolve().parents[1]

#: Tête attendue. Une divergence est un fait à expliquer, jamais à corriger en
#: modifiant une migration pour retomber sur le nombre voulu.
TETE_ATTENDUE = "20260826_0043"

#: Requêtes d'introspection. Chacune interroge le catalogue de PostgreSQL, donc
#: l'état réel, et non une déclaration.
_REQUETES: dict[str, str] = {
    "schemas": """
        SELECT nspname AS name FROM pg_namespace
        WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema'
        ORDER BY nspname
    """,
    "tables": """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """,
    "columns": """
        SELECT table_name, column_name, data_type, is_nullable,
               column_default, character_maximum_length, numeric_precision
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """,
    "primary_keys": """
        SELECT tc.table_name, tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public' AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY tc.table_name, kcu.ordinal_position
    """,
    "foreign_keys": """
        SELECT tc.table_name, tc.constraint_name, kcu.column_name,
               ccu.table_name AS references_table, ccu.column_name AS references_column,
               rc.delete_rule, rc.update_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_name = tc.constraint_name AND rc.constraint_schema = tc.table_schema
        WHERE tc.table_schema = 'public' AND tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.table_name, tc.constraint_name, kcu.column_name
    """,
    "unique_constraints": """
        SELECT tc.table_name, tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public' AND tc.constraint_type = 'UNIQUE'
        ORDER BY tc.table_name, tc.constraint_name, kcu.column_name
    """,
    "check_constraints": """
        SELECT rel.relname AS table_name, con.conname AS constraint_name,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'public' AND con.contype = 'c'
        ORDER BY rel.relname, con.conname
    """,
    "indexes": """
        SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
        FROM pg_indexes WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """,
    "views": """
        SELECT table_name AS name, 'view' AS kind
        FROM information_schema.views WHERE table_schema = 'public'
        UNION ALL
        SELECT matviewname AS name, 'materialized_view' AS kind
        FROM pg_matviews WHERE schemaname = 'public'
        ORDER BY name
    """,
    "sequences": """
        SELECT sequence_name AS name, data_type
        FROM information_schema.sequences WHERE sequence_schema = 'public'
        ORDER BY sequence_name
    """,
    "enums": """
        SELECT t.typname AS name, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) AS labels
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public'
        GROUP BY t.typname ORDER BY t.typname
    """,
    "functions": """
        SELECT p.proname AS name, pg_get_function_identity_arguments(p.oid) AS arguments
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' ORDER BY p.proname, arguments
    """,
    "triggers": """
        SELECT event_object_table AS table_name, trigger_name, event_manipulation, action_timing
        FROM information_schema.triggers WHERE trigger_schema = 'public'
        ORDER BY event_object_table, trigger_name, event_manipulation
    """,
    "extensions": """
        SELECT extname AS name, extversion AS version FROM pg_extension ORDER BY extname
    """,
    "rls_policies": """
        SELECT tablename AS table_name, policyname AS policy_name, cmd, qual, with_check
        FROM pg_policies WHERE schemaname = 'public'
        ORDER BY tablename, policyname
    """,
    "table_privileges": """
        SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privileges
        FROM information_schema.table_privileges
        WHERE table_schema = 'public'
        GROUP BY table_name, grantee ORDER BY table_name, grantee
    """,
}


def _git(*args: str) -> str:
    resultat = subprocess.run(
        ["git", *args], cwd=RACINE, capture_output=True, text=True, encoding="utf-8"
    )
    return resultat.stdout.strip() if resultat.returncode == 0 else "inconnu"


def introspecter(url: str) -> dict[str, Any]:
    """Interroge le catalogue PostgreSQL. Aucune donnée de table n'est lue."""
    from sqlalchemy import create_engine, text

    moteur = create_engine(url)
    resultats: dict[str, Any] = {}
    with moteur.connect() as connexion:
        version = connexion.execute(text("SELECT version()")).scalar()
        base = connexion.execute(text("SELECT current_database()")).scalar()
        for nom, requete in sorted(_REQUETES.items()):
            lignes = connexion.execute(text(requete)).mappings().all()
            resultats[nom] = [dict(ligne) for ligne in lignes]
    moteur.dispose()

    resultats["_database"] = {
        "server_version": (version or "").split(" on ")[0],
        "database_name": base,
    }
    return resultats


def graphe_alembic() -> dict[str, Any]:
    """Toutes les révisions, leurs parents, et le nombre de têtes.

    Le nombre de têtes est le point critique : deux têtes signifient que
    `upgrade head` est ambigu, et qu'une partie du schéma peut ne jamais être
    appliquée sans que rien ne le signale.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(RACINE / "alembic.ini"))
    config.set_main_option("script_location", str(RACINE / "alembic"))
    scripts = ScriptDirectory.from_config(config)

    revisions = []
    for revision in scripts.walk_revisions():
        parents = revision.down_revision
        if parents is None:
            liste_parents: list[str] = []
        elif isinstance(parents, str):
            liste_parents = [parents]
        else:
            liste_parents = sorted(parents)
        revisions.append(
            {
                "revision": revision.revision,
                "down_revisions": liste_parents,
                "is_merge_point": len(liste_parents) > 1,
                "is_branch_point": bool(revision.is_branch_point),
                "doc": (revision.doc or "").strip(),
            }
        )
    revisions.sort(key=lambda r: r["revision"])

    tetes = sorted(scripts.get_heads())
    ordre = [r.revision for r in scripts.walk_revisions()][::-1]
    return {
        "revision_count": len(revisions),
        "heads": tetes,
        "head_count": len(tetes),
        "single_head": len(tetes) == 1,
        "expected_head": TETE_ATTENDUE,
        "head_matches_expected": tetes == [TETE_ATTENDUE],
        "merge_points": [r["revision"] for r in revisions if r["is_merge_point"]],
        "branch_points": [r["revision"] for r in revisions if r["is_branch_point"]],
        "topological_order": ordre,
        "revisions": revisions,
    }


def _ecrire(chemin: Path, payload: Any) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "payload": payload},
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def _lire_payload(chemin: Path) -> Any:
    if not chemin.is_file():
        return None
    return json.loads(chemin.read_text(encoding="utf-8")).get("payload")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True, help="base PostgreSQL DÉJÀ migrée")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=RACINE / "artifacts" / "g0")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    if not (args.generate or args.check or args.print_summary):
        parser.error("choisir --generate, --check ou --print-summary")

    schema = introspecter(args.database_url)
    alembic = graphe_alembic()

    # La version du serveur et le nom de la base sont volatils : ils dépendent
    # de l'environnement de mesure, pas du code. Les comparer par `--check`
    # ferait échouer le contrôle sur un runner différent.
    infos_base = schema.pop("_database")

    if args.print_summary:
        print(f"PostgreSQL                     : {infos_base['server_version']}")
        print(f"Base introspectée              : {infos_base['database_name']}")
        for nom in sorted(schema):
            print(f"{nom:31s}: {len(schema[nom])}")
        print(f"{'revisions Alembic':31s}: {alembic['revision_count']}")
        print(f"{'têtes':31s}: {alembic['heads']} (unique={alembic['single_head']})")
        print(
            f"{'tête attendue':31s}: {alembic['expected_head']} "
            f"(correspond={alembic['head_matches_expected']})"
        )
        print(f"{'points de fusion':31s}: {alembic['merge_points'] or 'aucun'}")

    if args.generate:
        _ecrire(args.output_dir / "schema.json", schema)
        _ecrire(args.output_dir / "alembic-graph.json", alembic)
        (args.output_dir / "schema-provenance.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generator_version": GENERATOR_VERSION,
                    "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source_git_sha": _git("rev-parse", "HEAD"),
                    "generation_command": (
                        "python scripts/g0_schema_inventory.py --database-url <postgres> --generate"
                    ),
                    "platform": f"{platform.system().lower()}/{platform.machine().lower()}",
                    "postgres_server_version": infos_base["server_version"],
                    "database_name": infos_base["database_name"],
                    "_comment": (
                        "La version du serveur et le nom de la base dependent de "
                        "l'environnement de mesure : ils sont exclus du payload compare."
                    ),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nArtefacts écrits dans {args.output_dir}")

    echecs: list[str] = []
    if not alembic["single_head"]:
        echecs.append(f"Alembic a {alembic['head_count']} têtes : {alembic['heads']}")
    if not alembic["head_matches_expected"]:
        echecs.append(
            f"tête {alembic['heads']} != attendue [{TETE_ATTENDUE}] — "
            "expliquer l'écart, ne PAS modifier une migration pour le masquer"
        )

    if args.check:
        for nom, payload in (("schema", schema), ("alembic-graph", alembic)):
            versionne = _lire_payload(args.output_dir / f"{nom}.json")
            if versionne is None:
                echecs.append(f"{nom}.json absent")
            elif versionne != payload:
                echecs.append(f"{nom}.json diverge de la base introspectée")

    if echecs:
        print("\nECHEC :", file=sys.stderr)
        for message in echecs:
            print(f"  ! {message}", file=sys.stderr)
        return 1
    if args.check:
        print("\nLes artefacts versionnés correspondent à la base migrée.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

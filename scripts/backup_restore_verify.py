"""Sauvegarde / restauration PostgreSQL — semis et vérification multiplateformes.

Complément **multiplateforme** de ``scripts/pg_restore_verify.ps1`` (conservé, et
qui reste la procédure d'exploitation Windows/compose). Ce module n'a besoin que
de Python et d'une URL PostgreSQL : il tourne donc aussi bien en local que dans
GitHub Actions, où il porte le job « Sauvegarde et restauration PostgreSQL ».

Deux sous-commandes :

``seed``    peuple une base **jetable** de données strictement synthétiques et
            écrit un manifeste (comptages + relations attendues) ;
``verify``  relit une base **restaurée** et vérifie qu'elle est identique au
            manifeste : comptages, relations patient→ordre→échantillon→résultat,
            contraintes et index critiques.

Aucune donnée réelle n'est lue, produite ni exportée : les identités sont des
libellés de test explicites, et le module refuse de s'exécuter sur une base dont
le nom n'annonce pas son caractère jetable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

# Nom de la révision Alembic attendue. Aligné sur la tête du dépôt ; un test
# vérifie cet alignement (cf. tests/test_backup_restore_verify.py).
EXPECTED_ALEMBIC_HEAD = "20260826_0043"

# Garde-fou : ce module ne doit jamais viser une base d'exploitation.
_JETABLE_MARKERS = ("test", "verify", "restore", "scratch", "ci", "tmp")

# Jeu synthétique : 3 patients, 3 échantillons, 3 ordres, 4 items, 4 résultats.
_PATIENTS = [
    ("TEST-IPP-0001", "SYNTHETIQUE", "PatientUn", dt.date(1990, 1, 1), "F"),
    ("TEST-IPP-0002", "SYNTHETIQUE", "PatientDeux", dt.date(1985, 6, 15), "M"),
    ("TEST-IPP-0003", "SYNTHETIQUE", "PatientTrois", dt.date(2001, 12, 31), "F"),
]
_EXAMS = [("GLYC", "Glycemie"), ("NFS", "Hemogramme")]


class VerificationError(RuntimeError):
    """Écart constaté entre la base restaurée et le manifeste."""


def _guard_disposable(url: str) -> None:
    """Refuse toute base dont le nom n'annonce pas qu'elle est jetable."""
    dbname = url.rsplit("/", 1)[-1].split("?")[0].lower()
    if not any(marker in dbname for marker in _JETABLE_MARKERS):
        raise SystemExit(
            f"REFUS : la base '{dbname}' ne porte aucun marqueur de base jetable "
            f"({', '.join(_JETABLE_MARKERS)}). Ce script ne doit jamais viser une "
            "base d'exploitation."
        )


def _engine(url: str) -> Engine:
    _guard_disposable(url)
    return create_engine(url, future=True)


# ── semis ───────────────────────────────────────────────────────────────────


def seed(url: str, manifest_path: Path) -> dict:
    """Peuple la base jetable et renvoie (et écrit) le manifeste attendu.

    Le semis passe par l'**ORM**, à dessein : les colonnes NOT NULL dont le
    défaut est côté Python (``ordered_at``, ``analysis_date``, ``status``…) sont
    alors renseignées automatiquement, et le semis reste correct quand le modèle
    évolue. La vérification, elle, relit la base en **SQL brut** : elle contrôle
    ainsi ce que la base contient réellement, sans repasser par les mêmes
    hypothèses que le semis.
    """
    from sqlalchemy.orm import Session

    from app.models import ExamOrder, ExamOrderItem, Patient, Result, Sample

    engine = _engine(url)

    with Session(engine) as session:
        patients = [
            Patient(
                ipp_unique_id=ipp,
                last_name=last,
                first_name=first,
                birth_date=dob,
                birth_date_estimee=False,
                sex=sex,
            )
            for ipp, last, first, dob, sex in _PATIENTS
        ]
        session.add_all(patients)
        session.flush()

        samples = [
            Sample(barcode=f"TEST-BC-{i:04d}", patient_id=p.id, status="received")
            for i, p in enumerate(patients, start=1)
        ]
        session.add_all(samples)
        session.flush()

        orders, items, results = [], [], []
        for index, (patient, sample) in enumerate(zip(patients, samples, strict=True), start=1):
            order = ExamOrder(
                patient_id=patient.id,
                sample_id=sample.id,
                status="collected",
                requesting_service="TEST",
                priority="routine",
            )
            session.add(order)
            session.flush()
            orders.append(order)

            # Le premier ordre porte deux examens : la restauration doit préserver
            # la cardinalité 1-n, pas seulement des comptages globaux.
            for code, label in _EXAMS if index == 1 else _EXAMS[:1]:
                result = Result(
                    sample_id=sample.id,
                    exam_code=code,
                    data_points={code: {"value": 1.0, "unit": "g/L"}},
                    result_type="quantitative",
                    is_validated=True,
                )
                session.add(result)
                session.flush()
                results.append(result)

                item = ExamOrderItem(
                    order_id=order.id,
                    exam_code=code,
                    exam_label=label,
                    status="resulted",
                    result_id=result.id,
                )
                session.add(item)
                session.flush()
                items.append(item)

        session.commit()
        counts = {
            "patients": len(patients),
            "samples": len(samples),
            "exam_orders": len(orders),
            "exam_order_items": len(items),
            "results": len(results),
        }
        chain_rows = len(items)

    manifest = {
        "alembic_head": EXPECTED_ALEMBIC_HEAD,
        "counts": counts,
        # Chaîne complète attendue : chaque item remonte à son patient d'origine.
        "chain_rows": chain_rows,
        "orders_with_two_items": 1,
        "ipps": [p[0] for p in _PATIENTS],
        "barcodes": [f"TEST-BC-{i:04d}" for i in range(1, len(_PATIENTS) + 1)],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


# ── vérification ────────────────────────────────────────────────────────────

_CRITICAL_INDEXES = {
    "exam_orders": "ix_exam_orders_csa_prescription_id",
    "samples": "ix_samples_barcode",
    "patients": "ix_patients_ipp_unique_id",
}

# Requêtes de comptage pré-construites : les noms de table ne sont jamais
# interpolés depuis le manifeste, seulement recherchés dans cette table fermée.
_COUNTABLE_TABLES = {
    name: text(f"SELECT count(*) FROM {name}")  # noqa: S608 - littéraux du module
    for name in ("patients", "samples", "exam_orders", "exam_order_items", "results")
}


def _check(results: list[tuple[str, bool, str]], label: str, ok: bool, detail: str = "") -> None:
    results.append((label, ok, detail))


def verify(url: str, manifest_path: Path) -> list[tuple[str, bool, str]]:
    """Compare la base restaurée au manifeste. Renvoie la liste des contrôles."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    engine = _engine(url)
    checks: list[tuple[str, bool, str]] = []

    with engine.connect() as conn:
        # 1. Tête Alembic restaurée
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        _check(
            checks,
            "Tête Alembic",
            head == manifest["alembic_head"],
            f"trouvée={head} attendue={manifest['alembic_head']}",
        )

        # 2. Comptages exacts. Le nom de table vient du manifeste, mais on ne
        # l'interpole jamais sans l'avoir confronté à une liste fermée : un
        # manifeste altéré ne doit pas pouvoir devenir un vecteur d'injection.
        for table, expected in manifest["counts"].items():
            if table not in _COUNTABLE_TABLES:
                _check(checks, f"Comptage {table}", False, "table hors liste autorisée")
                continue
            actual = conn.execute(_COUNTABLE_TABLES[table]).scalar()
            _check(checks, f"Comptage {table}", actual == expected, f"{actual} vs {expected}")

        # 3. Chaîne patient → ordre → échantillon → résultat, jointe de bout en bout
        chain = conn.execute(
            text(
                "SELECT count(*) FROM exam_order_items i "
                "JOIN exam_orders o  ON i.order_id = o.id "
                "JOIN patients p     ON o.patient_id = p.id "
                "JOIN samples s      ON o.sample_id = s.id "
                "JOIN results r      ON i.result_id = r.id "
                "WHERE r.sample_id = s.id AND s.patient_id = p.id"
            )
        ).scalar()
        _check(
            checks,
            "Chaîne patient→ordre→échantillon→résultat",
            chain == manifest["chain_rows"],
            f"{chain} chaîne(s) complète(s) vs {manifest['chain_rows']}",
        )

        # 4. Cardinalité 1-n préservée (un ordre porte deux examens)
        multi = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT order_id FROM exam_order_items "
                "GROUP BY order_id HAVING count(*) = 2) x"
            )
        ).scalar()
        _check(
            checks,
            "Cardinalité 1-n des items",
            multi == manifest["orders_with_two_items"],
            f"{multi} ordre(s) à 2 items",
        )

        # 5. Aucun résultat rattaché au mauvais patient (cohérence inter-patients)
        orphelins = conn.execute(
            text(
                "SELECT count(*) FROM exam_orders o "
                "JOIN samples s ON o.sample_id = s.id "
                "WHERE s.patient_id IS DISTINCT FROM o.patient_id"
            )
        ).scalar()
        _check(
            checks, "Cohérence patient ordre/échantillon", orphelins == 0, f"{orphelins} écart(s)"
        )

        # 6. Identités synthétiques retrouvées à l'identique
        ipps = [
            row[0]
            for row in conn.execute(
                text("SELECT ipp_unique_id FROM patients ORDER BY ipp_unique_id")
            )
        ]
        _check(checks, "IPP restaurés", ipps == sorted(manifest["ipps"]), f"{ipps}")

        # 7. Contraintes : clés étrangères présentes sur les tables du fil
        inspector = inspect(engine)
        for table, expected_fk in (
            ("exam_orders", "patients"),
            ("exam_order_items", "exam_orders"),
            ("results", "samples"),
            ("samples", "patients"),
        ):
            cibles = {fk["referred_table"] for fk in inspector.get_foreign_keys(table)}
            _check(
                checks,
                f"Clé étrangère {table}→{expected_fk}",
                expected_fk in cibles,
                f"cibles={sorted(cibles)}",
            )

        # 8. Index critiques (dont l'unicité qui porte l'idempotence CSA)
        for table, index_name in _CRITICAL_INDEXES.items():
            noms = {ix["name"] for ix in inspector.get_indexes(table)}
            _check(checks, f"Index {index_name}", index_name in noms, f"présents={sorted(noms)}")

        unique_csa = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'exam_orders' "
                "AND indexname = 'ix_exam_orders_csa_prescription_id'"
            )
        ).scalar()
        _check(
            checks,
            "Unicité csa_prescription_id",
            bool(unique_csa) and "UNIQUE" in unique_csa.upper(),
            "index unique préservé" if unique_csa else "index absent",
        )

    return checks


def _report(checks: list[tuple[str, bool, str]]) -> bool:
    largeur = max(len(label) for label, _, _ in checks)
    for label, ok, detail in checks:
        marque = "OK  " if ok else "ECHEC"
        print(f"[{marque}] {label.ljust(largeur)}  {detail}")
    echecs = [label for label, ok, _ in checks if not ok]
    print()
    if echecs:
        print(f"VERDICT : ECHEC — {len(echecs)} contrôle(s) en échec : {', '.join(echecs)}")
        return False
    print(f"VERDICT : SUCCES — {len(checks)} contrôles passés")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="peuple une base jetable de données synthétiques")
    p_seed.add_argument("--url", required=True)
    p_seed.add_argument("--manifest", type=Path, default=Path("restore-manifest.json"))

    p_verify = sub.add_parser("verify", help="vérifie une base restaurée contre le manifeste")
    p_verify.add_argument("--url", required=True)
    p_verify.add_argument("--manifest", type=Path, default=Path("restore-manifest.json"))

    args = parser.parse_args(argv)

    if args.command == "seed":
        manifest = seed(args.url, args.manifest)
        print("Jeu synthétique créé :")
        for table, count in sorted(manifest["counts"].items()):
            print(f"  {table:20s} {count}")
        print(f"Manifeste écrit : {args.manifest}")
        return 0

    return 0 if _report(verify(args.url, args.manifest)) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

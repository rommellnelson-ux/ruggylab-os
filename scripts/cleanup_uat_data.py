"""Nettoyage des données UAT locales RuggyLab OS.

Par défaut le script est en dry-run. Utiliser ``--apply`` uniquement sur une
base de développement/staging dédiée.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models import AuditEvent, Patient, Result, Sample  # noqa: E402


def _ids(rows: list[object]) -> list[int]:
    return [row.id for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Supprime les données locales préfixées UAT-*.")
    parser.add_argument(
        "--apply", action="store_true", help="Applique réellement les suppressions."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        patients = list(
            db.scalars(select(Patient).where(Patient.ipp_unique_id.like("UAT-%"))).all()
        )
        patient_ids = _ids(patients)
        samples = list(
            db.scalars(
                select(Sample).where(
                    (Sample.barcode.like("UAT-%")) | (Sample.patient_id.in_(patient_ids))
                )
            ).all()
        )
        sample_ids = _ids(samples)
        results = list(db.scalars(select(Result).where(Result.sample_id.in_(sample_ids))).all())
        result_ids = _ids(results)
        audit_events = list(
            db.scalars(
                select(AuditEvent).where(
                    (
                        (AuditEvent.entity_type == "result")
                        & (AuditEvent.entity_id.in_(map(str, result_ids)))
                    )
                    | (
                        (AuditEvent.entity_type == "patient")
                        & (AuditEvent.entity_id.in_(map(str, patient_ids)))
                    )
                )
            ).all()
        )

        counts = {
            "patients": len(patients),
            "samples": len(samples),
            "results": len(results),
            "audit_events": len(audit_events),
        }
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"{mode} cleanup UAT: {counts}")

        if not args.apply:
            print("Aucune suppression effectuée. Relancer avec --apply pour appliquer.")
            return 0

        if audit_events:
            db.execute(delete(AuditEvent).where(AuditEvent.id.in_(_ids(audit_events))))
        if results:
            db.execute(delete(Result).where(Result.id.in_(result_ids)))
        if samples:
            db.execute(delete(Sample).where(Sample.id.in_(sample_ids)))
        if patients:
            db.execute(delete(Patient).where(Patient.id.in_(patient_ids)))
        db.commit()
        print("Nettoyage UAT appliqué.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

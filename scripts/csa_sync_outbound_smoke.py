"""Instance de TEST du flux SORTANT RuggyLab -> CSA (I2).

À lancer APRÈS csa_sync_smoke.py (l'ordre CSA doit déjà exister dans la base de
test). Ce script :
  1. simule le laboratoire : rattache un échantillon à l'ordre d'origine CSA et
     crée un résultat VALIDÉ pour chaque examen mappé ;
  2. exécute un cycle sortant réel : pousse les événements labo_resultats vers la
     Supabase CSA (compte RUGGYLAB) ;
  3. affiche ce qui a été remonté.

Base SQLite de test uniquement (même DATABASE_URL que le smoke entrant).
"""

from __future__ import annotations

import sys

from app.core.config import settings
from app.db.session import SessionLocal, configure_database
from app.models import ExamOrder, Result, Sample
from app.services.exam_catalog import exam_catalog_entry

# Valeurs de démonstration plausibles par examen (data_points structuré).
_DEMO_VALUES = {
    "NFS": {"WBC": {"value": 6.8, "unit": "10^9/L", "status": "N"},
            "HGB": {"value": 13.2, "unit": "g/dL", "status": "N"}},
    "GLYC": {"GLYC": {"value": 0.98, "unit": "g/L", "status": "N"}},
    "CHOL": {"CHOL": {"value": 1.85, "unit": "g/L", "status": "N"}},
    "TG": {"TG": {"value": 1.10, "unit": "g/L", "status": "N"}},
    "HDL": {"HDL": {"value": 0.55, "unit": "g/L", "status": "N"}},
    "LDL": {"LDL": {"value": 1.05, "unit": "g/L", "status": "N"}},
}


def main() -> int:
    if not settings.DATABASE_URL.startswith("sqlite"):
        print(f"REFUS: DATABASE_URL n'est pas SQLite ({settings.DATABASE_URL}).")
        return 2
    if not settings.CSA_RUGGYLAB_PASSWORD:
        print("REFUS: CSA_RUGGYLAB_PASSWORD absent (voir .env).")
        return 2

    configure_database(settings.DATABASE_URL)
    db = SessionLocal()
    try:
        order = (
            db.query(ExamOrder)
            .filter(ExamOrder.csa_prescription_id.isnot(None))
            .order_by(ExamOrder.id.desc())
            .first()
        )
        if order is None:
            print("Aucun ordre d'origine CSA en base. Lance d'abord csa_sync_smoke.py.")
            return 1

        # 1) Simulation labo : échantillon + résultats validés pour les items mappés.
        if order.sample_id is None:
            sample = Sample(barcode=f"DEMO-{order.id}", patient_id=order.patient_id, status="received")
            db.add(sample)
            db.flush()
            order.sample_id = sample.id
        created = 0
        for item in order.items:
            if item.exam_code.startswith("CSA:"):
                continue  # non mappé : pas de résultat
            already = (
                db.query(Result)
                .filter(Result.sample_id == order.sample_id, Result.exam_code == item.exam_code)
                .first()
            )
            if already:
                continue
            db.add(Result(
                sample_id=order.sample_id,
                exam_code=item.exam_code,
                data_points=_DEMO_VALUES.get(item.exam_code, {item.exam_code: {"value": 1.0, "status": "N"}}),
                result_type="quantitative",
                is_validated=True,
            ))
            created += 1
        db.commit()
        print(f"Labo simulé : échantillon {order.sample_id}, {created} résultat(s) validé(s) créé(s).\n")
    finally:
        db.close()

    # 2) Cycle sortant réel (login RUGGYLAB + push_event labo_resultats).
    from app.services.csa_sync.outbound import run_outbound_cycle

    print("--- Cycle de synchro sortant (résultats validés -> CSA) ---")
    summary = run_outbound_cycle()
    print(f"Résumé : {summary}\n")

    # 3) Restitution.
    db = SessionLocal()
    try:
        order = (
            db.query(ExamOrder)
            .filter(ExamOrder.csa_prescription_id.isnot(None))
            .order_by(ExamOrder.id.desc())
            .first()
        )
        print(f"Ordre #{order.id} (CSA presc {order.csa_prescription_id}) — items :")
        for it in order.items:
            marque = it.csa_pushed_at.isoformat() if it.csa_pushed_at else "—"
            label = (exam_catalog_entry(it.exam_code) or {}).get("label", it.exam_label)
            print(f"   · {it.exam_code:12s} statut={it.status:9s} remonté_le={marque}  ({label})")
    finally:
        db.close()
    print("\nOK — cycle sortant terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

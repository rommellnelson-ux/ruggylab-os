"""Instance de TEST du flux entrant CSA -> RuggyLab (I0/I1).

Isolé et jetable : crée le schéma RuggyLab dans une base SQLite dédiée (variable
DATABASE_URL), exécute UN cycle de synchro réel contre la Supabase CSA (login
compte RUGGYLAB via GoTrue, RPC pull/push), puis affiche ce qui est arrivé.

À lancer avec les variables d'environnement de connexion CSA déjà posées
(le mot de passe est lu depuis .env, jamais depuis la ligne de commande).

    python scripts/csa_sync_smoke.py

Ne modifie AUCUNE base de production : DATABASE_URL doit pointer sur un fichier
SQLite de test.
"""

from __future__ import annotations

import sys

from app.core.config import settings
from app.db.base_class import Base
from app.db.session import configure_database, engine

# Importer le package modèles enregistre toutes les tables sur Base.metadata.
import app.models  # noqa: F401,E402
from app.models import ExamOrder, Patient  # noqa: E402


def main() -> int:
    if not settings.DATABASE_URL.startswith("sqlite"):
        print(f"REFUS: DATABASE_URL n'est pas SQLite ({settings.DATABASE_URL}).")
        print("Ce script de test ne doit jamais tourner sur une vraie base.")
        return 2
    if not settings.CSA_SUPABASE_URL:
        print("REFUS: CSA_SUPABASE_URL non configuré.")
        return 2
    if not settings.CSA_RUGGYLAB_PASSWORD:
        print("REFUS: CSA_RUGGYLAB_PASSWORD absent.")
        print("Ajoute la ligne CSA_RUGGYLAB_PASSWORD=<mot de passe> dans le .env,")
        print("puis relance. (Ce script ne l'affiche jamais.)")
        return 2

    # (Re)configure la session sur la base de test et crée le schéma.
    configure_database(settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    print(f"Base de test : {settings.DATABASE_URL}")
    print(f"Cible CSA    : {settings.CSA_SUPABASE_URL}")
    print(f"Compte       : {settings.CSA_RUGGYLAB_EMAIL}\n")

    from app.services.csa_sync.inbound import run_sync_cycle

    print("--- Cycle de synchro entrant (pull -> apply -> accusé) ---")
    summary = run_sync_cycle()
    print(f"Résumé : {summary}\n")

    # Restitution lisible de ce qui est arrivé dans RuggyLab.
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        patients = db.query(Patient).all()
        orders = db.query(ExamOrder).all()
        print(f"Patients créés/mis à jour : {len(patients)}")
        for p in patients:
            ddn = f"{p.birth_date} (estimée)" if p.birth_date_estimee else str(p.birth_date)
            print(f"  - {p.ipp_unique_id} : {p.last_name} {p.first_name} | sexe={p.sex} | né(e) {ddn}")
        print(f"\nOrdres d'examen créés : {len(orders)}")
        for o in orders:
            print(f"  Ordre #{o.id} (CSA presc {o.csa_prescription_id}) "
                  f"prio={o.priority} statut={o.status} service={o.requesting_service}")
            for it in o.items:
                flag = "  <-- NON MAPPÉ" if it.status == "unmapped" else ""
                print(f"      · {it.exam_code:12s} {it.exam_label}  [{it.status}]{flag}")
    finally:
        db.close()
    print("\nOK — cycle terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

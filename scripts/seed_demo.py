"""Jeu de données de démonstration pour l'UAT.

Amorce les référentiels (bioref, cibles TAT, correspondances de codes, règle
d'auto-validation), importe un registre synthétique réaliste, puis crée quelques
résultats « riches » (valeurs numériques + horodatages TAT + qualitatif) afin que
les testeurs disposent immédiatement de matière pour tous les scénarios A–F.

Données entièrement fictives. À exécuter sur une instance de TEST :

    SECRET_KEY=... FIRST_SUPERUSER_PASSWORD=... DATABASE_URL=... \
        python -m scripts.seed_demo
"""

from __future__ import annotations

import datetime as dt

from app.db.session import SessionLocal
from app.models import Patient, Result, Sample, User
from app.services.bioref_service import seed_bioref
from app.services.bootstrap import init_db
from app.services.code_mapping_service import apply_bioref_to_result, seed_mappings
from app.services.tat_service import seed_default_targets
from app.utils.datetime_utils import utcnow_naive

# Registre synthétique (format identique au Registre_Maitre réel).
DEMO_REGISTRE_ROWS: list[dict] = [
    {
        "nom": "KONÉ Awa",
        "date": "05/01/2026",
        "type_registre": "CMU",
        "age": "34 ans",
        "examens": "NFS ; CRP négative",
        "montant": 7000,
        "part_cmu": 4900,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "BROU Yao",
        "date": "05/01/2026",
        "type_registre": "Hors CMU",
        "age": "52 ans",
        "examens": "Glycémie 1,45 ; Créat 11,2 ; Urée 0,38",
        "montant": 9000,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "DIABATÉ Fatou",
        "date": "06/01/2026",
        "type_registre": "CMU",
        "age": "28 ans",
        "examens": "GE +120 trophozoïtes/champ ; NFS",
        "montant": 5000,
        "part_cmu": 3500,
        "prescripteur": "Adj. Bamba",
    },
    {
        "nom": "KOUASSI Jean",
        "date": "07/01/2026",
        "type_registre": "Hors CMU",
        "age": "61 ans",
        "examens": "ASAT 48 ; ALAT 52 ; GGT 70",
        "montant": 12000,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "TRAORÉ Mariam",
        "date": "08/01/2026",
        "type_registre": "CMU",
        "age": "45 ans",
        "examens": "Cholestérol 2,3 ; HDL 0,38 ; LDL 1,6 ; Triglycérides 1,8",
        "montant": 11000,
        "part_cmu": 7700,
        "prescripteur": "Chef Bénie",
    },
    {
        "nom": "N'GUESSAN Paul",
        "date": "12/02/2026",
        "type_registre": "Hors CMU",
        "age": "39 ans",
        "examens": "GE négative ; CRP 12",
        "montant": 5000,
        "prescripteur": "Inf. Coulibaly",
    },
    {
        "nom": "OUATTARA Salif",
        "date": "12/02/2026",
        "type_registre": "CMU",
        "age": "70 ans",
        "examens": "Ionogramme ; Créat 14,5",
        "montant": 8000,
        "part_cmu": 5600,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "ASSI Chantal",
        "date": "15/02/2026",
        "type_registre": "CMU",
        "age": "31 ans",
        "examens": "AgHBs négatif ; VIH négatif",
        "montant": 6000,
        "part_cmu": 4200,
        "prescripteur": "Adj. Essoh",
    },
    {
        "nom": "BAMBA Issouf",
        "date": "03/03/2026",
        "type_registre": "Hors CMU",
        "age": "55 ans",
        "examens": "HbA1c 7,8 ; Glycémie 1,9",
        "montant": 9500,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "YAO Akissi",
        "date": "03/03/2026",
        "type_registre": "CMU",
        "age": "26 ans",
        "examens": "NFS ; GE +60 ; CRP 8",
        "montant": 7000,
        "part_cmu": 4900,
        "prescripteur": "Chef Bérénice",
    },
    {
        "nom": "KOFFI Eric",
        "date": "10/03/2026",
        "type_registre": "Hors CMU",
        "age": "48 ans",
        "examens": "Acide urique 78 ; Créat 13",
        "montant": 6500,
        "prescripteur": "Dr Wognin",
    },
    {
        "nom": "SANGARÉ Aminata",
        "date": "10/03/2026",
        "type_registre": "CMU",
        "age": "37 ans",
        "examens": "TPHA négatif ; VDRL négatif",
        "montant": 6000,
        "part_cmu": 4200,
        "prescripteur": "Adj. Bamba",
    },
]

# Résultats « riches » : (nom, sexe, exam_code, data_points, statut TAT visé).
DEMO_RICH = [
    ("DÉMO Hémato F", "F", "NFS", {"HB": 10.5, "HCT": 33, "WBC": 6.2, "PLT": 240}, "on_time"),
    ("DÉMO Glycémie", "M", "GLYC", {"GLYC": 0.32}, "late"),  # critique bas
    ("DÉMO Paludisme", "M", "GE", {"MAL_GE": "positive"}, "on_time"),
    ("DÉMO Iono", "F", "IONO", {"NA": 128, "K": 6.6, "CL": 100}, "on_time"),  # K critique haut
]


def _admin(db) -> User:
    return db.query(User).filter(User.username == "admin").first()


def _make_rich_result(db, user, name, sex, exam_code, data_points, tat_kind) -> None:
    patient = Patient(
        ipp_unique_id=f"DEMO-{exam_code}-{utcnow_naive().strftime('%H%M%S%f')}",
        first_name="Démo",
        last_name=name,
        birth_date=dt.date(1985, 6, 15),
        sex=sex,
    )
    db.add(patient)
    db.flush()
    now = utcnow_naive()
    registered = now - dt.timedelta(minutes=(200 if tat_kind == "late" else 35))
    sample = Sample(
        barcode=f"DEMO-S-{exam_code}-{now.strftime('%H%M%S%f')}",
        patient_id=patient.id,
        collection_date=registered,
        received_date=registered + dt.timedelta(minutes=5),
        status="Démo",
    )
    db.add(sample)
    db.flush()
    result = Result(
        sample_id=sample.id,
        exam_code=exam_code,
        data_points=data_points,
        is_validated=True,
        validator_id=user.id if user else None,
        analysis_date=now,
        registered_at=registered,
        collected_at=registered,
        received_at=registered + dt.timedelta(minutes=5),
        analysis_started_at=now - dt.timedelta(minutes=20),
        analysis_finished_at=now - dt.timedelta(minutes=5),
        bio_validated_at=now,
    )
    db.add(result)
    db.flush()
    apply_bioref_to_result(db, result)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        n_bio = seed_bioref(db)
        n_tat = seed_default_targets(db)
        n_map = seed_mappings(db)
        admin = _admin(db)

        from app.services.registre_import import import_registre_rows
        from app.services.registre_parser import build_import_preview

        preview = build_import_preview(DEMO_REGISTRE_ROWS)
        report = import_registre_rows(db, DEMO_REGISTRE_ROWS, user=admin, dry_run=False)

        for spec in DEMO_RICH:
            _make_rich_result(db, admin, *spec)
        db.commit()

        print("=== Jeu de démonstration UAT chargé ===")
        print(f"  Référentiels : bioref={n_bio}, cibles TAT={n_tat}, mappings={n_map}")
        print(
            f"  Registre : {report['created_patients']} patients, "
            f"{report['created_results']} résultats "
            f"(reconnaissance {preview['recognized_exams']}/{preview['total_exams']} examens)"
        )
        print(f"  Résultats riches (TAT + bioref) : {len(DEMO_RICH)}")
        print("  -> Connectez-vous au cockpit et explorez Résultats / TAT / Registre.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

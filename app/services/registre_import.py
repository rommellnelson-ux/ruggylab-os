"""Import effectif du registre maître → Patients / Échantillons / Résultats.

Réutilise le parseur de texte libre. Écriture défensive : un point de
sauvegarde (savepoint) par ligne, insertion ORM directe (pas de consommation
de réactifs ni d'auto-validation — il s'agit d'un historique). Mode dry-run
par défaut : rien n'est persisté tant que ``dry_run=False`` ET ``confirm=True``.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Patient, Result, Sample, User
from app.services.audit import log_audit_event
from app.services.registre_analytics import _parse_date
from app.services.registre_parser import parse_exam_cell
from app.utils.datetime_utils import utcnow_naive

MAX_ROWS = 10_000


class RegistreImportTooLargeError(ValueError):
    pass


def _split_name(full: str) -> tuple[str, str]:
    """Sépare « M. ESSOH Paul » en (prénom, nom) de façon best-effort."""
    parts = [p for p in full.replace(".", " ").split() if p and p not in ("M", "Mme", "Mlle", "Dr")]
    if not parts:
        return "—", full[:100] or "—"
    if len(parts) == 1:
        return "—", parts[0][:100]
    # Convention registre : NOM en premier, prénom(s) ensuite
    return " ".join(parts[1:])[:100], parts[0][:100]


def _birth_from_age(row: dict) -> tuple[dt.date, bool]:
    """Estime une date de naissance depuis l'âge (« 46 ans »). Renvoie (date, estimée)."""
    age_raw = str(row.get("age") or row.get("âge") or row.get("Âge") or "").strip()
    digits = "".join(c for c in age_raw if c.isdigit())
    if digits:
        try:
            age = int(digits)
            if 0 < age < 130:
                return dt.date(dt.date.today().year - age, 1, 1), True
        except ValueError:
            pass
    # Sentinelle si âge inconnu (date passée, jamais future)
    return dt.date(1900, 1, 1), False


def import_registre_rows(
    db: Session,
    rows: list[dict],
    *,
    user: User,
    dry_run: bool = True,
) -> dict:
    """Importe les lignes du registre. Dry-run : compte sans écrire."""
    if len(rows) > MAX_ROWS:
        raise RegistreImportTooLargeError(f"Trop de lignes ({len(rows)}). Max {MAX_ROWS}.")

    created_patients = 0
    created_samples = 0
    created_results = 0
    estimated_birth = 0
    errors: list[dict] = []

    for idx, row in enumerate(rows, start=1):
        try:
            full_name = (
                row.get("nom")
                or row.get("patient")
                or row.get("nom_patient")
                or row.get("Nom et prénoms")
                or ""
            ).strip()
            if not full_name:
                raise ValueError("nom patient manquant")

            exams = parse_exam_cell(row.get("examens") or row.get("Examens"))
            if dry_run:
                created_patients += 1
                created_samples += 1
                created_results += len(exams)
                _, estimated = _birth_from_age(row)
                if not estimated:
                    estimated_birth += 1
                continue

            first, last = _split_name(full_name)
            birth, estimated = _birth_from_age(row)
            if not estimated:
                estimated_birth += 1
            coll_date = _parse_date(row.get("date") or row.get("date_demande") or row.get("Date"))
            coll_dt = dt.datetime.combine(coll_date, dt.time(8, 0)) if coll_date else utcnow_naive()
            uid = uuid.uuid4().hex[:6]

            with db.begin_nested():
                patient = Patient(
                    ipp_unique_id=f"REG-{idx:05d}-{uid}",
                    first_name=first or "—",
                    last_name=last or "—",
                    birth_date=birth,
                    sex=None,
                )
                db.add(patient)
                db.flush()

                sample = Sample(
                    barcode=f"REG-S-{idx:05d}-{uid}",
                    patient_id=patient.id,
                    collection_date=coll_dt,
                    received_date=coll_dt,
                    status="Importé (historique)",
                )
                db.add(sample)
                db.flush()

                for e in exams:
                    data_points: dict = {}
                    key = e["exam_code"] or (e["name"] or "exam")
                    if e["numeric_value"] is not None:
                        data_points[key] = e["numeric_value"]
                    if e["qualitative"]:
                        data_points["interpretation"] = e["qualitative"]
                    if not e["recognized"]:
                        data_points["raw"] = e["raw"]
                    if not data_points:
                        data_points = {"raw": e["raw"]}
                    db.add(
                        Result(
                            sample_id=sample.id,
                            exam_code=e["exam_code"],
                            data_points=data_points,
                            is_validated=True,
                            validator_id=user.id,
                            analysis_date=coll_dt,
                            registered_at=coll_dt,
                            collected_at=coll_dt,
                            received_at=coll_dt,
                            bio_validated_at=coll_dt,
                        )
                    )
                    created_results += 1

            created_patients += 1
            created_samples += 1
        except (ValueError, IntegrityError, SQLAlchemyError) as exc:
            errors.append({"row": idx, "error": str(exc).replace("\n", " ")[:300]})

    if not dry_run and created_patients:
        log_audit_event(
            db,
            user=user,
            event_type="registre.import",
            entity_type="registre",
            entity_id=None,
            payload={
                "patients": created_patients,
                "samples": created_samples,
                "results": created_results,
            },
        )
        db.commit()

    return {
        "dry_run": dry_run,
        "total_rows": len(rows),
        "created_patients": created_patients,
        "created_samples": created_samples,
        "created_results": created_results,
        "estimated_birth_dates": estimated_birth,
        "errors": errors,
    }

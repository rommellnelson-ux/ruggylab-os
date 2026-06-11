"""Import en lot depuis CSV : patients et réactifs.

Chaque ligne est validée via les schémas Pydantic existants puis insérée.
Le résultat détaille les lignes créées et, pour chaque échec, le numéro de
ligne et le message d'erreur — sans interrompre le traitement des autres lignes.

Transaction : tout est committé en fin de traitement (un seul commit). Les
lignes invalides sont ignorées et n'empêchent pas l'insertion des lignes valides.
"""

from __future__ import annotations

import csv
import datetime as dt
from io import StringIO

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Patient, Reagent
from app.schemas.patient import PatientCreate
from app.schemas.reagent import ReagentCreate

# Borne dure pour éviter un traitement synchrone trop lourd / un déni de service.
MAX_ROWS = 5000


class BulkImportTooLargeError(ValueError):
    """Levée quand le CSV dépasse MAX_ROWS lignes de données."""


def _clean(value: str | None) -> str | None:
    """Trim + convertit les chaînes vides en None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_rows(csv_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(csv_text))
    rows = [{(k or "").strip(): (v or "") for k, v in row.items()} for row in reader]
    if len(rows) > MAX_ROWS:
        raise BulkImportTooLargeError(
            f"Trop de lignes ({len(rows)}). Maximum autorisé : {MAX_ROWS}."
        )
    return rows


def _finalize(db: Session, *, created: int, total: int, errors: list[dict], dry_run: bool) -> dict:
    """Commit si import réel (dry_run ne persiste jamais rien) et renvoie le rapport."""
    if not dry_run and created:
        db.commit()
    return {"total": total, "created": created, "errors": errors, "dry_run": dry_run}


def import_patients(db: Session, csv_text: str, *, dry_run: bool = False) -> dict:
    """Importe des patients depuis un CSV.

    Colonnes attendues : ipp_unique_id, first_name, last_name, birth_date (YYYY-MM-DD),
    sex (F/M, optionnel), rank (optionnel).

    Chaque ligne est insérée dans un point de sauvegarde (savepoint) : une ligne
    invalide ou en conflit n'empêche pas l'insertion des autres. En mode
    ``dry_run``, rien n'est persisté (validation à blanc).
    """
    rows = _parse_rows(csv_text)
    created = 0
    errors: list[dict] = []
    seen_ipp: set[str] = set()

    for idx, raw in enumerate(rows, start=2):  # ligne 1 = en-tête
        try:
            ipp = _clean(raw.get("ipp_unique_id"))
            if not ipp:
                raise ValueError("ipp_unique_id manquant")
            if ipp in seen_ipp:
                raise ValueError(f"IPP dupliqué dans le fichier : {ipp}")
            if db.query(Patient).filter(Patient.ipp_unique_id == ipp).first():
                raise ValueError(f"Patient déjà existant pour l'IPP {ipp}")

            payload = PatientCreate(
                ipp_unique_id=ipp,
                first_name=_clean(raw.get("first_name")) or "",
                last_name=_clean(raw.get("last_name")) or "",
                birth_date=dt.date.fromisoformat(_clean(raw.get("birth_date")) or ""),
                sex=_clean(raw.get("sex")),
                rank=_clean(raw.get("rank")),
            )
            if not dry_run:
                with db.begin_nested():  # savepoint par ligne (isole les conflits DB)
                    db.add(Patient(**payload.model_dump()))
                    db.flush()  # déclenche les contraintes DB ici, dans le savepoint
            seen_ipp.add(ipp)
            created += 1
        except (ValidationError, ValueError, IntegrityError, SQLAlchemyError) as exc:
            errors.append({"row": idx, "error": str(exc).replace("\n", " ")[:300]})

    return _finalize(db, created=created, total=len(rows), errors=errors, dry_run=dry_run)


def import_reagents(db: Session, csv_text: str, *, dry_run: bool = False) -> dict:
    """Importe des réactifs depuis un CSV.

    Colonnes attendues : name, category, unit, current_stock, alert_threshold,
    lot_number, expiry_date (YYYY-MM-DD), supplier. Seul ``name`` est obligatoire.
    Insertion par savepoint ; ``dry_run`` ne persiste rien.
    """
    rows = _parse_rows(csv_text)
    created = 0
    errors: list[dict] = []
    seen_names: set[str] = set()

    def _to_float(val: str | None, default: float = 0.0) -> float:
        val = _clean(val)
        return float(val) if val is not None else default

    for idx, raw in enumerate(rows, start=2):
        try:
            name = _clean(raw.get("name"))
            if not name:
                raise ValueError("name manquant")
            if name in seen_names:
                raise ValueError(f"Réactif dupliqué dans le fichier : {name}")
            if db.query(Reagent).filter(Reagent.name == name).first():
                raise ValueError(f"Réactif déjà existant : {name}")

            expiry_raw = _clean(raw.get("expiry_date"))
            payload = ReagentCreate(
                name=name,
                category=_clean(raw.get("category")),
                unit=_clean(raw.get("unit")) or "unit",
                current_stock=_to_float(raw.get("current_stock")),
                alert_threshold=_to_float(raw.get("alert_threshold")),
                lot_number=_clean(raw.get("lot_number")),
                expiry_date=dt.date.fromisoformat(expiry_raw) if expiry_raw else None,
                supplier=_clean(raw.get("supplier")),
            )
            if not dry_run:
                with db.begin_nested():  # savepoint par ligne (isole les conflits DB)
                    db.add(Reagent(**payload.model_dump()))
                    db.flush()
            seen_names.add(name)
            created += 1
        except (ValidationError, ValueError, IntegrityError, SQLAlchemyError) as exc:
            errors.append({"row": idx, "error": str(exc).replace("\n", " ")[:300]})

    return _finalize(db, created=created, total=len(rows), errors=errors, dry_run=dry_run)

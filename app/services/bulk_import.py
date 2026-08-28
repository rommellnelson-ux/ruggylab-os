"""Import en lot depuis CSV : patients et réactifs.

Chaque ligne est validée via les schémas Pydantic existants puis insérée.
Le résultat détaille les lignes créées et, pour chaque échec, le numéro de
ligne et le message d'erreur — sans interrompre le traitement des autres lignes.

Transaction : tout est committé en fin de traitement (un seul commit). Les
lignes invalides sont ignorées et n'empêchent pas l'insertion des lignes valides.
"""

from __future__ import annotations

import csv
from io import StringIO

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Patient, Reagent
from app.schemas.patient import PatientCreate
from app.schemas.reagent import ReagentCreate
from app.utils.import_errors import message as import_message
from app.utils.import_errors import parse_date, parse_decimal

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
        # ── Validation EN AMONT : ce qu'on sait vérifier soi-même produit un
        # code métier, pas une exception. On n'a donc rien à rattraper — et rien
        # à exposer qui vienne d'un objet exception.
        ipp = _clean(raw.get("ipp_unique_id"))
        if not ipp:
            errors.append({"row": idx, "error": import_message("identifiant_manquant")})
            continue
        if ipp in seen_ipp:
            errors.append({"row": idx, "error": import_message("identifiant_duplique")})
            continue
        if db.query(Patient).filter(Patient.ipp_unique_id == ipp).first():
            errors.append({"row": idx, "error": import_message("deja_existant")})
            continue

        naissance, code = parse_date(_clean(raw.get("birth_date")))
        if naissance is None:
            errors.append({"row": idx, "error": import_message(code or "date_invalide")})
            continue

        try:
            payload = PatientCreate(
                ipp_unique_id=ipp,
                first_name=_clean(raw.get("first_name")) or "",
                last_name=_clean(raw.get("last_name")) or "",
                birth_date=naissance,
                sex=_clean(raw.get("sex")),
                rank=_clean(raw.get("rank")),
            )
            if not dry_run:
                with db.begin_nested():  # savepoint par ligne (isole les conflits DB)
                    db.add(Patient(**payload.model_dump()))
                    db.flush()  # déclenche les contraintes DB ici, dans le savepoint
            seen_ipp.add(ipp)
            created += 1
        # L'exception n'est volontairement PAS liée (`as exc`) : rien de ce
        # qu'elle porte ne doit pouvoir atteindre la réponse.
        except (ValidationError, ValueError):
            errors.append({"row": idx, "error": import_message("donnees_invalides")})
        except (IntegrityError, SQLAlchemyError):
            errors.append({"row": idx, "error": import_message("erreur_base")})

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
        # Validation en amont (voir import_patients) : codes métier, pas d'exception.
        name = _clean(raw.get("name"))
        if not name:
            errors.append({"row": idx, "error": import_message("identifiant_manquant")})
            continue
        if name in seen_names:
            errors.append({"row": idx, "error": import_message("identifiant_duplique")})
            continue
        if db.query(Reagent).filter(Reagent.name == name).first():
            errors.append({"row": idx, "error": import_message("deja_existant")})
            continue

        peremption = None
        expiry_raw = _clean(raw.get("expiry_date"))
        if expiry_raw:
            peremption, code = parse_date(expiry_raw)
            if peremption is None:
                errors.append({"row": idx, "error": import_message(code or "date_invalide")})
                continue

        code = None
        for champ in ("current_stock", "alert_threshold"):
            _, code = parse_decimal(_clean(raw.get(champ)))
            if code is not None:
                break
        if code is not None:
            errors.append({"row": idx, "error": import_message(code)})
            continue

        try:
            payload = ReagentCreate(
                name=name,
                category=_clean(raw.get("category")),
                unit=_clean(raw.get("unit")) or "unit",
                current_stock=_to_float(raw.get("current_stock")),
                alert_threshold=_to_float(raw.get("alert_threshold")),
                lot_number=_clean(raw.get("lot_number")),
                expiry_date=peremption,
                supplier=_clean(raw.get("supplier")),
            )
            if not dry_run:
                with db.begin_nested():  # savepoint par ligne (isole les conflits DB)
                    db.add(Reagent(**payload.model_dump()))
                    db.flush()
            seen_names.add(name)
            created += 1
        # Exception non liée : rien de ce qu'elle porte n'atteint la réponse.
        except (ValidationError, ValueError):
            errors.append({"row": idx, "error": import_message("donnees_invalides")})
        except (IntegrityError, SQLAlchemyError):
            errors.append({"row": idx, "error": import_message("erreur_base")})

    return _finalize(db, created=created, total=len(rows), errors=errors, dry_run=dry_run)

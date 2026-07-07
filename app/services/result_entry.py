"""Préparation de la saisie des résultats depuis prescription et équipement."""

from __future__ import annotations

import datetime as dt
import unicodedata

from sqlalchemy.orm import Session, selectinload

from app.models import BiologicalCodeMapping, Equipment, ExamOrder, Patient, Sample
from app.services.bioref_service import find_reference, format_reference_range
from app.services.code_mapping_data import CODE_MAPPING_SEED
from app.services.exam_catalog import exam_catalog_entry
from app.services.exam_order_service import sync_order_progress
from app.services.units import canonical_unit

_BIOCHEMISTRY = {
    "GLYC",
    "UREE",
    "CREAT",
    "ALAT",
    "ASAT",
    "CHOL",
    "HDL",
    "LDL",
    "TG",
    "HBA1C",
    "URIC",
    "CALC",
    "CRP",
}
_SEROLOGY = {"AGHBS", "HIV", "WIDAL"}


def _norm(text: str | None) -> str:
    return (
        unicodedata.normalize("NFKD", text or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )


def equipment_exam_codes(equipment: Equipment) -> set[str]:
    """Retourne les examens compatibles avec un type d'équipement connu."""
    descriptor = f"{_norm(equipment.name)} {_norm(equipment.type)}"
    if "dh36" in descriptor or "hematolog" in descriptor or "nfs" in descriptor:
        return {"NFS"}
    if "precis" in descriptor:
        return {"GLYC", "CHOL", "URIC"}
    if "iono" in descriptor or "electrolyt" in descriptor:
        return {"IONO", "CALC"}
    if "biochimi" in descriptor or "spectro" in descriptor:
        return set(_BIOCHEMISTRY) | {"IONO"}
    if "serolog" in descriptor or "immuno" in descriptor:
        return set(_SEROLOGY) | {"CRP"}
    if "microscop" in descriptor or "parasit" in descriptor:
        return {"GE", "ECBU"}
    if "vs" in descriptor or "sediment" in descriptor:
        return {"VS"}
    if "electrophor" in descriptor:
        return {"ELPHB"}
    if "groupage" in descriptor or "blood bank" in descriptor:
        return {"GRH"}
    return set()


def equipment_supports_exam(equipment: Equipment, exam_code: str) -> bool:
    return exam_code.upper() in equipment_exam_codes(equipment)


def _age(patient: Patient | None) -> float | None:
    if patient is None or patient.birth_date is None:
        return None
    return (dt.date.today() - patient.birth_date).days / 365.25


def _active_mapping(db: Session, exam_code: str) -> BiologicalCodeMapping | None:
    return (
        db.query(BiologicalCodeMapping)
        .filter(
            BiologicalCodeMapping.exam_code == exam_code,
            BiologicalCodeMapping.is_active.is_(True),
        )
        .order_by(BiologicalCodeMapping.priority)
        .first()
    )


def _field_from_mapping(
    db: Session,
    mapping: BiologicalCodeMapping,
    patient: Patient | None,
) -> dict:
    ref = (
        find_reference(db, mapping.test_code, patient.sex, _age(patient))
        if mapping.test_code
        else None
    )
    if ref is None and mapping.test_code and patient and patient.sex in {"M", "F"}:
        suffix = "H" if patient.sex == "M" else "F"
        ref = find_reference(
            db, f"{mapping.test_code}_{suffix}", patient.sex, _age(patient)
        )
    key = mapping.analyte_code or mapping.canonical_code
    qualitative = bool(ref and ref.normal_text and ref.lower_limit is None and ref.upper_limit is None)
    return {
        "key": key,
        "label": mapping.label or mapping.canonical_code,
        "kind": "qualitative" if qualitative else "number",
        "unit": canonical_unit((ref.unit if ref else None) or mapping.unit),
        "reference_range": format_reference_range(ref) if ref else None,
        "options": ["Négatif", "Positif"] if qualitative else [],
        "reference_available": ref is not None,
    }


_SPECIAL_FIELDS: dict[str, list[dict]] = {
    "VS": [{"key": "VS", "label": "Vitesse de sédimentation", "kind": "number", "unit": "mm/h"}],
    "WIDAL": [
        {
            "key": "WIDAL",
            "label": "Résultat / titres Widal",
            "kind": "text",
            "unit": None,
            "options": [],
        }
    ],
    "GRH": [
        {
            "key": "GRH",
            "label": "Groupe ABO-RhD",
            "kind": "choice",
            "unit": None,
            "options": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        }
    ],
    "ELPHB": [
        {
            "key": "ELPHB",
            "label": "Profil d’électrophorèse",
            "kind": "text",
            "unit": None,
            "options": [],
        }
    ],
    "ECBU": [
        {
            "key": "ECBU",
            "label": "Conclusion ECBU / germe et antibiogramme",
            "kind": "text",
            "unit": None,
            "options": [],
        }
    ],
}


def result_fields_for_exam(db: Session, exam_code: str, patient: Patient | None) -> list[dict]:
    code = exam_code.upper()
    mapping = _active_mapping(db, code)
    if mapping is None:
        return _SPECIAL_FIELDS.get(
            code,
            [{"key": code, "label": code, "kind": "text", "unit": None, "options": []}],
        )
    if mapping.is_panel:
        components = (
            db.query(BiologicalCodeMapping)
            .filter(
                BiologicalCodeMapping.component_of == mapping.canonical_code,
                BiologicalCodeMapping.is_active.is_(True),
            )
            .order_by(BiologicalCodeMapping.priority, BiologicalCodeMapping.id)
            .all()
        )
        return [_field_from_mapping(db, component, patient) for component in components]
    if mapping.test_code is None:
        return _SPECIAL_FIELDS.get(
            code,
            [
                {
                    "key": mapping.analyte_code or code,
                    "label": mapping.label or code,
                    "kind": "text",
                    "unit": canonical_unit(mapping.unit),
                    "options": [],
                }
            ],
        )
    return [_field_from_mapping(db, mapping, patient)]


def validate_result_payload(
    db: Session,
    exam_code: str,
    data_points: dict,
    patient: Patient | None,
) -> None:
    """Vérifie que les analytes saisis appartiennent bien à l'examen."""
    if exam_catalog_entry(exam_code) is None:
        return
    code = exam_code.upper()
    exam_mappings = [item for item in CODE_MAPPING_SEED if item.get("exam_code") == code]
    allowed: set[str] = set()
    for mapping in exam_mappings:
        candidates = (
            [
                item
                for item in CODE_MAPPING_SEED
                if item.get("component_of") == mapping["canonical_code"]
            ]
            if mapping.get("is_panel")
            else [mapping]
        )
        for candidate in candidates:
            allowed.update(
                str(value).upper()
                for value in (
                    candidate.get("analyte_code"),
                    candidate.get("test_code"),
                    candidate.get("canonical_code"),
                    candidate.get("exam_code"),
                )
                if value
            )
    if not allowed:
        allowed = {
            str(field["key"]).upper()
            for field in result_fields_for_exam(db, exam_code, patient)
        }
    submitted = {
        str(key).upper()
        for key in data_points
        if key not in {"overall_flags", "calibration", "manual_entry_by", "entry_timestamp"}
    }
    if not submitted:
        raise ValueError("Aucune valeur analytique saisie.")
    unknown = sorted(submitted - allowed)
    if unknown:
        raise ValueError(
            f"Analyte(s) incompatible(s) avec l'examen {exam_code}: {', '.join(unknown)}."
        )


def build_result_entry_context(db: Session, sample: Sample) -> dict:
    """Construit la liste des examens encore attendus pour cet échantillon."""
    order = (
        db.query(ExamOrder)
        .options(selectinload(ExamOrder.items))
        .filter(ExamOrder.sample_id == sample.id, ExamOrder.status != "cancelled")
        .order_by(ExamOrder.ordered_at.desc(), ExamOrder.id.desc())
        .first()
    )
    if order:
        sync_order_progress(db, order)

    equipment = db.query(Equipment).order_by(Equipment.name, Equipment.id).all()
    exams = []
    if order:
        for item in order.items:
            if item.status != "pending":
                continue
            code = item.exam_code.upper()
            catalog = exam_catalog_entry(code) or {}
            exams.append(
                {
                    "order_id": order.id,
                    "order_item_id": item.id,
                    "exam_code": code,
                    "exam_label": item.exam_label or catalog.get("label") or code,
                    "fields": result_fields_for_exam(db, code, sample.patient),
                    "compatible_equipment_ids": [
                        machine.id for machine in equipment if equipment_supports_exam(machine, code)
                    ],
                }
            )

    return {
        "sample_id": sample.id,
        "sample_barcode": sample.barcode,
        "patient_id": sample.patient_id,
        "order_id": order.id if order else None,
        "order_priority": order.priority if order else None,
        "exams": exams,
        "equipment": [
            {
                "id": machine.id,
                "name": machine.name,
                "type": machine.type,
                "supported_exam_codes": sorted(equipment_exam_codes(machine)),
            }
            for machine in equipment
        ],
    }


def linked_order_for_sample(db: Session, sample_id: int) -> ExamOrder | None:
    return (
        db.query(ExamOrder)
        .options(selectinload(ExamOrder.items))
        .filter(ExamOrder.sample_id == sample_id, ExamOrder.status != "cancelled")
        .order_by(ExamOrder.ordered_at.desc(), ExamOrder.id.desc())
        .first()
    )


def validate_prescribed_exam(db: Session, sample_id: int, exam_code: str) -> ExamOrder | None:
    """Refuse un examen non prescrit lorsqu'un bon est lié à l'échantillon."""
    order = linked_order_for_sample(db, sample_id)
    if order is None:
        return None
    expected = {
        item.exam_code.upper()
        for item in order.items
        if item.status != "cancelled" and item.result_id is None
    }
    if exam_code.upper() not in expected:
        raise ValueError(f"L'examen {exam_code} n'est pas en attente sur la prescription liée.")
    return order

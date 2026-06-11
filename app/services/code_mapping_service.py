"""Service d'unification des vocabulaires biologiques.

Relie exam_code ↔ test_code ↔ analyte via ``BiologicalCodeMapping`` et applique
une interprétation bioref **complémentaire** au cycle de vie du résultat, sans
modifier le moteur existant (ReferenceRange/compute_flags, CriticalRange).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import BiologicalCodeMapping, BiologicalReferenceRange
from app.services.bioref_service import (
    find_reference,
    format_reference_range,
    interpret_value,
    normalize_sex,
)
from app.services.code_mapping_data import CODE_MAPPING_SEED


# ── Résolveurs ──────────────────────────────────────────────────────────────

def _active(db: Session):
    return db.query(BiologicalCodeMapping).filter(BiologicalCodeMapping.is_active.is_(True))


def resolve_from_exam_code(db: Session, exam_code: str | None) -> BiologicalCodeMapping | None:
    if not exam_code:
        return None
    return (
        _active(db)
        .filter(BiologicalCodeMapping.exam_code == exam_code)
        .order_by(BiologicalCodeMapping.priority)
        .first()
    )


def resolve_from_test_code(db: Session, test_code: str | None) -> BiologicalCodeMapping | None:
    if not test_code:
        return None
    return (
        _active(db)
        .filter(BiologicalCodeMapping.test_code == test_code)
        .order_by(BiologicalCodeMapping.priority)
        .first()
    )


def resolve_from_analyte(db: Session, analyte_code: str | None) -> BiologicalCodeMapping | None:
    if not analyte_code:
        return None
    return (
        _active(db)
        .filter(BiologicalCodeMapping.analyte_code == analyte_code)
        .order_by(BiologicalCodeMapping.priority)
        .first()
    )


def get_components(db: Session, panel_code: str) -> list[BiologicalCodeMapping]:
    """Composants d'un panel (par canonical_code du panel)."""
    return (
        _active(db)
        .filter(BiologicalCodeMapping.component_of == panel_code)
        .order_by(BiologicalCodeMapping.priority, BiologicalCodeMapping.canonical_code)
        .all()
    )


def get_canonical_code(
    db: Session, *, exam_code: str | None = None, test_code: str | None = None,
    analyte_code: str | None = None,
) -> str | None:
    """Renvoie le canonical_code à partir de n'importe quel vocabulaire."""
    for resolver, value in (
        (resolve_from_exam_code, exam_code),
        (resolve_from_test_code, test_code),
        (resolve_from_analyte, analyte_code),
    ):
        if value:
            m = resolver(db, value)
            if m:
                return m.canonical_code
    return None


def _find_bioref(db: Session, test_code: str | None, sex, age) -> BiologicalReferenceRange | None:
    """Trouve la valeur de référence, avec pont sexe (URIC→URIC_H/F, RBC→RBC_H/F)."""
    if not test_code:
        return None
    ref = find_reference(db, test_code, sex, age)
    if ref is None and sex:
        suffix = "H" if normalize_sex(sex) == "Homme" else "F"
        ref = find_reference(db, f"{test_code}_{suffix}", sex, age)
    return ref


def get_bioref_code_for_result(
    db: Session, exam_code: str | None, analyte_code: str | None = None, sex: str | None = None
) -> str | None:
    """test_code bioref applicable pour un (exam_code[, analyte_code]).

    Pour un panel + analyte fourni, renvoie le test_code du composant.
    """
    mapping = None
    if analyte_code:
        mapping = resolve_from_analyte(db, analyte_code)
    if mapping is None:
        mapping = resolve_from_exam_code(db, exam_code)
    if mapping is None:
        return None
    if mapping.is_panel and analyte_code:
        comp = (
            _active(db)
            .filter(
                BiologicalCodeMapping.component_of == mapping.canonical_code,
                BiologicalCodeMapping.analyte_code == analyte_code,
            )
            .first()
        )
        if comp:
            return comp.test_code
    return mapping.test_code


# ── Extraction de valeur + interprétation ───────────────────────────────────

def _to_number(raw) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        return _to_number(raw.get("value"))
    if isinstance(raw, str):
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            return None
    return None


def _find_value(data_points: dict, keys: list[str | None]) -> float | None:
    for k in keys:
        if k and k in data_points:
            v = _to_number(data_points[k])
            if v is not None:
                return v
    return None


def _patient_context(result) -> tuple[str | None, float | None]:
    patient = result.sample.patient if result.sample else None
    if not patient:
        return None, None
    sex = patient.sex
    age = None
    if patient.birth_date:
        today = dt.date.today()
        age = today.year - patient.birth_date.year - (
            (today.month, today.day) < (patient.birth_date.month, patient.birth_date.day)
        )
    return sex, age


def _interpret_one(db, test_code, value, sex, age) -> dict | None:
    ref = _find_bioref(db, test_code, sex, age)
    if ref is None:
        return None
    flag = interpret_value(value, ref)
    return {
        "test_code": ref.test_code,
        "value": value,
        "bioref_status": flag,
        "bioref_reference_range": format_reference_range(ref),
        "bioref_comment": ref.interpretation,
        "bioref_source": ref.source,
    }


def interpret_result_bioref(db: Session, result) -> dict | None:
    """Interprétation bioref complémentaire d'un résultat.

    - Panel : interprétation composant par composant (Hb, Ht, WBC, … / Na, K, …).
    - Test simple : interprétation unique (qualitatif si pas de valeur numérique).
    Ne modifie pas flags/is_critical ; renvoie une structure additive (ou None).
    """
    if not result.exam_code:
        return None
    mapping = resolve_from_exam_code(db, result.exam_code)
    if mapping is None:
        return None
    sex, age = _patient_context(result)
    dp = result.data_points or {}

    if mapping.is_panel:
        components: list[dict] = []
        for comp in get_components(db, mapping.canonical_code):
            value = _find_value(dp, [comp.analyte_code, comp.test_code, comp.canonical_code])
            if value is None:
                continue
            interp = _interpret_one(db, comp.test_code, value, sex, age)
            if interp:
                interp["component"] = comp.label or comp.canonical_code
                interp["canonical_code"] = comp.canonical_code
                components.append(interp)
        return {
            "is_panel": True,
            "canonical_code": mapping.canonical_code,
            "components": components,
            "primary": None,
        }

    # Test simple : valeur numérique si présente, sinon qualitatif (None)
    value = _find_value(dp, [mapping.analyte_code, mapping.exam_code, mapping.test_code,
                             mapping.canonical_code])
    interp = _interpret_one(db, mapping.test_code, value, sex, age)
    return {
        "is_panel": False,
        "canonical_code": mapping.canonical_code,
        "components": [interp] if interp else [],
        "primary": interp,
    }


def apply_bioref_to_result(db: Session, result) -> bool:
    """Renseigne les colonnes bioref_* du résultat (test simple uniquement).

    Pour un panel, les colonnes plates restent nulles (le détail par composant
    est fourni par l'endpoint dédié). Retourne True si un statut a été posé.
    """
    outcome = interpret_result_bioref(db, result)
    if not outcome or outcome["primary"] is None:
        return False
    p = outcome["primary"]
    result.bioref_status = p["bioref_status"]
    result.bioref_comment = p["bioref_comment"]
    result.bioref_reference_range = p["bioref_reference_range"]
    result.bioref_source = p["bioref_source"]
    return True


# ── Seed + orphelins ────────────────────────────────────────────────────────

def seed_mappings(db: Session) -> int:
    """Insère les correspondances absentes (idempotent). Retourne le nombre créé."""
    created = 0
    for spec in CODE_MAPPING_SEED:
        exists = (
            db.query(BiologicalCodeMapping)
            .filter(BiologicalCodeMapping.canonical_code == spec["canonical_code"])
            .first()
        )
        if exists:
            continue
        db.add(BiologicalCodeMapping(**spec))
        created += 1
    if created:
        db.commit()
    return created


def find_orphans(db: Session) -> dict:
    """Codes des catalogues sans correspondance dans la table de mapping."""
    from app.services.bioref_data import BIOREF_SEED
    from app.services.exam_catalog import EXAM_CATALOG

    mapped_exam = {
        m.exam_code for m in _active(db).filter(BiologicalCodeMapping.exam_code.isnot(None)).all()
    }
    mapped_test = {
        m.test_code for m in _active(db).filter(BiologicalCodeMapping.test_code.isnot(None)).all()
    }
    exam_codes = {e["code"] for e in EXAM_CATALOG}
    test_codes = {r["test_code"] for r in BIOREF_SEED}
    return {
        "exam_codes_unmapped": sorted(exam_codes - mapped_exam),
        "test_codes_unmapped": sorted(test_codes - mapped_test),
    }


def list_active(db: Session) -> list[BiologicalCodeMapping]:
    return (
        _active(db)
        .order_by(BiologicalCodeMapping.priority, BiologicalCodeMapping.canonical_code)
        .all()
    )

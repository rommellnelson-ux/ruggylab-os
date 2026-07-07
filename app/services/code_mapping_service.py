"""Service d'unification des vocabulaires biologiques.

Relie exam_code ↔ test_code ↔ analyte via ``BiologicalCodeMapping`` et applique
une interprétation bioref **complémentaire** au cycle de vie du résultat, sans
modifier le moteur existant (ReferenceRange/compute_flags, CriticalRange).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Query, Session

from app.models import BiologicalCodeMapping, BiologicalReferenceRange, Result
from app.services.bioref_service import (
    find_reference,
    format_reference_range,
    interpret_value,
    normalize_sex,
)
from app.services.code_mapping_data import CODE_MAPPING_SEED
from app.services.units import canonical_unit, convert_value

# ── Résolveurs ──────────────────────────────────────────────────────────────


def _active(db: Session) -> Query[BiologicalCodeMapping]:
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
    db: Session,
    *,
    exam_code: str | None = None,
    test_code: str | None = None,
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


def _find_bioref(
    db: Session, test_code: str | None, sex: str | None, age: float | None
) -> BiologicalReferenceRange | None:
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


def _to_number(raw: object) -> float | None:
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


def _find_measurement(
    data_points: dict, keys: list[str | None]
) -> tuple[float | None, str | None]:
    for k in keys:
        if k and k in data_points:
            raw = data_points[k]
            v = _to_number(raw)
            if v is not None:
                unit = raw.get("unit") if isinstance(raw, dict) else None
                return v, unit if isinstance(unit, str) else None
    return None, None


def _qual_token(raw: object) -> str | None:
    """Détecte un résultat qualitatif positif/négatif depuis une chaîne."""
    if isinstance(raw, dict):
        raw = raw.get("value")
    if not isinstance(raw, str):
        return None
    low = raw.strip().lower()
    if not low:
        return None
    if "posit" in low or low in ("+", "++", "+++", "réactif", "reactif"):
        return "positive"
    if "négat" in low or "negat" in low or low in ("-", "absent", "nég", "neg"):
        return "negative"
    return None


def _find_qualitative(data_points: dict, keys: list[str | None]) -> str | None:
    for k in keys:
        if k and k in data_points:
            tok = _qual_token(data_points[k])
            if tok is not None:
                return tok
    return None


def _qualitative_status(qual: str, ref: BiologicalReferenceRange) -> str:
    """Statut d'un test qualitatif vs son texte normal (souvent « Négatif »)."""
    normal_is_negative = (
        "égati" in (ref.normal_text or "").lower() or "egati" in (ref.normal_text or "").lower()
    )
    if qual == "positive":
        return "POSITIF (anormal)" if normal_is_negative else "POSITIF"
    # négatif
    return "NÉGATIF" if normal_is_negative else "NÉGATIF (anormal)"


def _patient_context(result: Result) -> tuple[str | None, float | None]:
    patient = result.sample.patient if result.sample else None
    if not patient:
        return None, None
    sex = patient.sex
    age = None
    if patient.birth_date:
        today = dt.date.today()
        age = (
            today.year
            - patient.birth_date.year
            - ((today.month, today.day) < (patient.birth_date.month, patient.birth_date.day))
        )
    return sex, age


def _interpret_one(
    db: Session,
    test_code: str | None,
    value: float | None,
    sex: str | None,
    age: float | None,
    qualitative: str | None = None,
    source_unit: str | None = None,
) -> dict | None:
    ref = _find_bioref(db, test_code, sex, age)
    if ref is None:
        return None
    # Valeur numérique → bornes ; sinon résultat qualitatif positif/négatif ;
    # sinon repli sur le texte normal de la référence.
    converted_value = value
    unit_compatible = True
    if value is not None:
        converted_value, unit_compatible = convert_value(value, source_unit, ref.unit)
    if value is None and qualitative is not None:
        flag = _qualitative_status(qualitative, ref)
    elif not unit_compatible:
        flag = "UNITÉ INCOMPATIBLE"
    else:
        flag = interpret_value(converted_value, ref)
    return {
        "test_code": ref.test_code,
        "value": converted_value,
        "unit": canonical_unit(ref.unit),
        "source_value": value,
        "source_unit": canonical_unit(source_unit),
        "unit_compatible": unit_compatible,
        "bioref_status": flag,
        "bioref_reference_range": format_reference_range(ref),
        "bioref_comment": ref.interpretation,
        "bioref_source": ref.source,
    }


def interpret_result_bioref(db: Session, result: Result) -> dict | None:
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
            comp_keys = [comp.analyte_code, comp.test_code, comp.canonical_code]
            value, source_unit = _find_measurement(dp, comp_keys)
            qual = _find_qualitative(dp, comp_keys) if value is None else None
            if value is None and qual is None:
                continue
            interp = _interpret_one(
                db, comp.test_code, value, sex, age, qual, source_unit
            )
            if interp:
                interp["component"] = comp.label or comp.canonical_code
                interp["canonical_code"] = comp.canonical_code
                interp["analyte_code"] = comp.analyte_code or comp.canonical_code
                components.append(interp)
        return {
            "is_panel": True,
            "canonical_code": mapping.canonical_code,
            "components": components,
            "primary": None,
        }

    # Test simple : valeur numérique si présente, sinon résultat qualitatif
    simple_keys = [
        mapping.analyte_code,
        mapping.exam_code,
        mapping.test_code,
        mapping.canonical_code,
    ]
    value, source_unit = _find_measurement(dp, simple_keys)
    qual = _find_qualitative(dp, simple_keys) if value is None else None
    interp = _interpret_one(db, mapping.test_code, value, sex, age, qual, source_unit)
    if interp:
        interp["component"] = mapping.label or mapping.canonical_code
        interp["canonical_code"] = mapping.canonical_code
        interp["analyte_code"] = mapping.analyte_code or mapping.canonical_code
    return {
        "is_panel": False,
        "canonical_code": mapping.canonical_code,
        "components": [interp] if interp else [],
        "primary": interp,
    }


def apply_bioref_to_result(db: Session, result: Result) -> bool:
    """Applique l'interprétation canonique au résultat.

    Le même référentiel pilote désormais les flags d'affichage et la criticité.
    Le drapeau critique manuel/configurable reste cumulatif : cette fonction ne
    remet jamais une valeur déjà critique à ``False``.
    """
    outcome = interpret_result_bioref(db, result)
    if not outcome:
        return False
    components = [item for item in outcome.get("components", []) if item]
    primary = outcome.get("primary")
    if primary:
        result.bioref_status = primary["bioref_status"]
        result.bioref_comment = primary["bioref_comment"]
        result.bioref_reference_range = primary["bioref_reference_range"]
        result.bioref_source = primary["bioref_source"]

    statuses = {
        str(item.get("canonical_code") or item.get("test_code")): item["bioref_status"]
        for item in components
        if item.get("bioref_status")
    }
    if statuses:
        result.flags = statuses
    if any(str(status).startswith("CRITIQUE") for status in statuses.values()):
        result.is_critical = True
    status_codes = {
        "NORMAL": "N",
        "BAS": "L",
        "HAUT": "H",
        "CRITIQUE BAS": "LL",
        "CRITIQUE HAUT": "HH",
        "NÉGATIF": "N",
        "POSITIF (ANORMAL)": "H",
        "UNITÉ INCOMPATIBLE": "U",
    }
    enriched_points = dict(result.data_points or {})
    for item in components:
        key = item.get("analyte_code") or item.get("canonical_code")
        if not key or key not in enriched_points:
            continue
        raw = enriched_points[key]
        point = dict(raw) if isinstance(raw, dict) else {"value": raw}
        item_status = str(item.get("bioref_status") or "")
        point["status"] = status_codes.get(item_status.upper(), item_status)
        point["ref_range"] = item.get("bioref_reference_range")
        point["is_critical"] = item_status.startswith("CRITIQUE")
        if not point.get("unit") and item.get("unit"):
            point["unit"] = item["unit"]
        enriched_points[key] = point
    result.data_points = enriched_points
    return bool(primary or components)


# ── Seed + orphelins ────────────────────────────────────────────────────────


def seed_mappings(db: Session) -> int:
    """Insère ou complète les correspondances par défaut.

    Retourne le nombre de lignes créées. Les lignes existantes sont aussi
    synchronisées pour éviter qu'une base initialisée avec un ancien seed garde
    des champs ``exam_code``/``test_code`` manquants.
    """
    created = 0
    for spec in CODE_MAPPING_SEED:
        mapping = (
            db.query(BiologicalCodeMapping)
            .filter(
                BiologicalCodeMapping.canonical_code == spec["canonical_code"],
                BiologicalCodeMapping.component_of == spec.get("component_of"),
            )
            .first()
        )
        if mapping:
            for field, value in spec.items():
                if value is not None and getattr(mapping, field) != value:
                    setattr(mapping, field, value)
            mapping.is_active = True
            continue
        db.add(BiologicalCodeMapping(**spec))
        created += 1
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

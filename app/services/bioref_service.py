"""Référentiel biologique : sélection de la valeur de référence + interprétation.

Porte la logique d'interprétation fournie (flags NORMAL / BAS / HAUT /
CRITIQUE BAS / CRITIQUE HAUT) et produit la sortie structurée attendue
(result, unit, reference_range, flag, interpretation).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import BiologicalReferenceRange
from app.services.bioref_data import BIOREF_SEED

_SEX_INPUT = {
    "M": "Homme",
    "H": "Homme",
    "HOMME": "Homme",
    "MALE": "Homme",
    "F": "Femme",
    "FEMME": "Femme",
    "FEMALE": "Femme",
    "ALL": "ALL",
    "": "ALL",
}


def normalize_sex(sex: str | None) -> str:
    if sex is None:
        return "ALL"
    return _SEX_INPUT.get(sex.strip().upper(), "ALL")


def interpret_value(value: float | None, ref: BiologicalReferenceRange) -> str:
    """Renvoie le flag d'interprétation pour ``value`` selon ``ref``.

    Reproduit la logique de référence : les seuils critiques priment sur les
    bornes normales ; un test qualitatif (valeur None) renvoie son texte normal.
    """
    if value is None:
        return ref.normal_text or "N/A"
    if ref.critical_low is not None and value < ref.critical_low:
        return "CRITIQUE BAS"
    if ref.critical_high is not None and value > ref.critical_high:
        return "CRITIQUE HAUT"
    if ref.lower_limit is not None and value < ref.lower_limit:
        return "BAS"
    if ref.upper_limit is not None and value > ref.upper_limit:
        return "HAUT"
    return "NORMAL"


def format_reference_range(ref: BiologicalReferenceRange) -> str:
    """Chaîne lisible de la plage de référence (ou texte normal qualitatif)."""
    if ref.normal_text:
        return ref.normal_text
    unit = ref.unit or ""
    lo, hi = ref.lower_limit, ref.upper_limit
    if lo is not None and hi is not None:
        return f"{lo:g} - {hi:g} {unit}".strip()
    if hi is not None:
        return f"< {hi:g} {unit}".strip()
    if lo is not None:
        return f"> {lo:g} {unit}".strip()
    return unit or "—"


def find_reference(
    db: Session, test_code: str, sex: str | None = None, age_years: float | None = None
) -> BiologicalReferenceRange | None:
    """Sélectionne la meilleure valeur de référence active.

    Filtre par code, sexe (spécifique prioritaire sur ALL) et tranche d'âge.
    """
    norm_sex = normalize_sex(sex)
    rows = (
        db.query(BiologicalReferenceRange)
        .filter(
            BiologicalReferenceRange.test_code == test_code,
            BiologicalReferenceRange.is_active.is_(True),
        )
        .all()
    )
    if not rows:
        return None

    def _matches(r: BiologicalReferenceRange) -> bool:
        if r.sex not in ("ALL", norm_sex):
            return False
        return age_years is None or (r.age_min_years <= age_years <= r.age_max_years)

    candidates = [r for r in rows if _matches(r)]
    if not candidates:
        # repli : ignorer l'âge si aucune tranche ne correspond
        candidates = [r for r in rows if r.sex in ("ALL", norm_sex)] or rows
    # Préfère une référence sexe-spécifique à une référence générique
    candidates.sort(key=lambda r: 0 if r.sex == norm_sex and norm_sex != "ALL" else 1)
    return candidates[0]


def interpret(
    db: Session,
    test_code: str,
    value: float | None,
    sex: str | None = None,
    age_years: float | None = None,
) -> dict:
    """Interprète une valeur et renvoie la sortie structurée.

    {result, unit, reference_range, flag, interpretation, test_name, source}
    ou {error} si aucune référence n'est trouvée.
    """
    ref = find_reference(db, test_code, sex, age_years)
    if ref is None:
        return {"error": f"Aucune référence pour le test '{test_code}'."}
    flag = interpret_value(value, ref)
    return {
        "test_code": ref.test_code,
        "test_name": ref.test_name,
        "result": value,
        "unit": ref.unit,
        "reference_range": format_reference_range(ref),
        "flag": flag,
        "interpretation": ref.interpretation,
        "source": ref.source,
    }


def seed_bioref(db: Session) -> int:
    """Insère les valeurs de référence absentes. Retourne le nombre créé (idempotent)."""
    created = 0
    for spec in BIOREF_SEED:
        exists = (
            db.query(BiologicalReferenceRange)
            .filter(
                BiologicalReferenceRange.test_code == spec["test_code"],
                BiologicalReferenceRange.sex == spec["sex"],
                BiologicalReferenceRange.age_min_years == spec["age_min_years"],
                BiologicalReferenceRange.age_max_years == spec["age_max_years"],
            )
            .first()
        )
        if exists:
            continue
        db.add(BiologicalReferenceRange(**spec))
        created += 1
    if created:
        db.commit()
    return created

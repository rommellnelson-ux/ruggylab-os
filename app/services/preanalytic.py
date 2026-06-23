"""Interférences pré-analytiques : un aspect d'échantillon non conforme fausse
certains analytes. Sert à alerter (non bloquant) et à commenter le compte-rendu.
"""

from __future__ import annotations

# Analytes (codes normalisés MAJUSCULES) faussés par un aspect donné.
ASPECT_INTERFERENCES: dict[str, set[str]] = {
    "hemolyse": {"K", "POTASSIUM", "KALIEMIE", "LDH", "AST", "ASAT", "TGO", "PHOSPHORE", "PHOS"},
    "lipemique": {"HB", "HEMOGLOBINE", "PROTEINES", "PROT", "TRIGLYCERIDES", "TG"},
    "icterique": {"CREATININE", "CREAT", "CHOLESTEROL", "CHOL", "BILIRUBINE"},
}

ASPECT_LABELS: dict[str, str] = {
    "conforme": "conforme",
    "hemolyse": "hémolysé",
    "icterique": "ictérique",
    "lipemique": "lipémique",
    "coagule": "coagulé",
    "insuffisant": "insuffisant",
}


def aspect_label(aspect: str | None) -> str:
    return ASPECT_LABELS.get(aspect or "", aspect or "")


def interfering_analytes(aspect: str | None, data_points: dict | None) -> list[str]:
    """Analytes présents dans ``data_points`` faussés par ``aspect`` (peut être vide)."""
    if not aspect:
        return []
    affected = ASPECT_INTERFERENCES.get(aspect)
    if not affected:
        return []
    return sorted(k for k in (data_points or {}) if str(k).strip().upper() in affected)


def interference_warning(aspect: str | None, data_points: dict | None) -> str | None:
    """Message d'avertissement (non bloquant) si l'aspect fausse des analytes saisis."""
    hits = interfering_analytes(aspect, data_points)
    if not hits:
        return None
    return (
        f"Échantillon {aspect_label(aspect)} : résultat(s) {', '.join(hits)} "
        "potentiellement faussé(s) — interpréter avec prudence."
    )

"""Catalogue d'examens biologiques — dérivé du registre maître réel.

Les codes et fréquences proviennent de l'analyse du registre historique du
laboratoire (NFS, Goutte épaisse, CRP, Urée, Glycémie, transaminases,
Créatinine, bilan lipidique, AgHBs, HbA1c, ionogramme…). Sert de référentiel
unique pour :
  - les codes d'examen (``Result.exam_code``)
  - les délais cibles TAT (``TatTarget``)
  - le rapprochement LOINC (export FHIR)
  - les listes déroulantes du cockpit

Aucune donnée patient ici : uniquement la nomenclature des examens.
"""

from __future__ import annotations

# Chaque entrée : code canonique, libellé, catégorie, LOINC (si connu),
# délai cible TAT en minutes, facteur d'alerte (orange jusqu'à cible × facteur).
EXAM_CATALOG: list[dict] = [
    # ── Hématologie ──────────────────────────────────────────────────────────
    {
        "code": "NFS",
        "label": "Numération Formule Sanguine",
        "category": "Hématologie",
        "loinc": "58410-2",
        "tat_minutes": 60,
        "warn_factor": 1.5,
    },
    {
        "code": "GE",
        "label": "Goutte épaisse (paludisme)",
        "category": "Parasitologie",
        "loinc": "32207-3",
        "tat_minutes": 60,
        "warn_factor": 1.5,
    },
    {
        "code": "VS",
        "label": "Vitesse de sédimentation",
        "category": "Hématologie",
        "loinc": "4537-7",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    # ── Inflammation / sérologie ─────────────────────────────────────────────
    {
        "code": "CRP",
        "label": "Protéine C-réactive",
        "category": "Biochimie",
        "loinc": "1988-5",
        "tat_minutes": 60,
        "warn_factor": 1.5,
    },
    {
        "code": "AGHBS",
        "label": "Antigène HBs",
        "category": "Sérologie",
        "loinc": "5196-1",
        "tat_minutes": 240,
        "warn_factor": 1.5,
    },
    {
        "code": "WIDAL",
        "label": "Sérodiagnostic de Widal",
        "category": "Sérologie",
        "loinc": None,
        "tat_minutes": 240,
        "warn_factor": 1.5,
    },
    # ── Biochimie de routine ─────────────────────────────────────────────────
    {
        "code": "GLYC",
        "label": "Glycémie",
        "category": "Biochimie",
        "loinc": "2345-7",
        "tat_minutes": 30,
        "warn_factor": 1.5,
    },
    {
        "code": "UREE",
        "label": "Urée sanguine",
        "category": "Biochimie",
        "loinc": "22664-7",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "CREAT",
        "label": "Créatinine",
        "category": "Biochimie",
        "loinc": "2160-0",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "ALAT",
        "label": "ALAT (transaminase)",
        "category": "Biochimie",
        "loinc": "1742-6",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "ASAT",
        "label": "ASAT (transaminase)",
        "category": "Biochimie",
        "loinc": "1920-8",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "IONO",
        "label": "Ionogramme sanguin",
        "category": "Biochimie",
        "loinc": "24326-1",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    # ── Bilan lipidique ──────────────────────────────────────────────────────
    {
        "code": "CHOL",
        "label": "Cholestérol total",
        "category": "Biochimie",
        "loinc": "2093-3",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "HDL",
        "label": "Cholestérol HDL",
        "category": "Biochimie",
        "loinc": "2085-9",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "LDL",
        "label": "Cholestérol LDL",
        "category": "Biochimie",
        "loinc": "2089-1",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "TG",
        "label": "Triglycérides",
        "category": "Biochimie",
        "loinc": "2571-8",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    # ── Diabète ──────────────────────────────────────────────────────────────
    {
        "code": "HBA1C",
        "label": "Hémoglobine glyquée (HbA1c)",
        "category": "Biochimie",
        "loinc": "4548-4",
        "tat_minutes": 240,
        "warn_factor": 1.5,
    },
    {
        "code": "URIC",
        "label": "Acide urique",
        "category": "Biochimie",
        "loinc": "3084-1",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    {
        "code": "CALC",
        "label": "Calcémie",
        "category": "Biochimie",
        "loinc": "17861-6",
        "tat_minutes": 120,
        "warn_factor": 1.5,
    },
    # ── Immuno-hématologie / sérologie ───────────────────────────────────────
    {
        "code": "GRH",
        "label": "Groupe sanguin Rhésus",
        "category": "Immuno-hématologie",
        "loinc": "882-1",
        "tat_minutes": 60,
        "warn_factor": 1.5,
    },
    {
        "code": "ELPHB",
        "label": "Électrophorèse de l'hémoglobine",
        "category": "Hématologie",
        "loinc": "4576-5",
        "tat_minutes": 24 * 60,
        "warn_factor": 1.2,
    },
    {
        "code": "HIV",
        "label": "Sérologie VIH",
        "category": "Sérologie",
        "loinc": "75622-1",
        "tat_minutes": 240,
        "warn_factor": 1.5,
    },
    # ── Microbiologie ────────────────────────────────────────────────────────
    {
        "code": "ECBU",
        "label": "ECBU (uroculture)",
        "category": "Microbiologie",
        "loinc": "630-4",
        "tat_minutes": 72 * 60,
        "warn_factor": 1.0,
    },
]

# Index par code pour lookup rapide
EXAM_BY_CODE: dict[str, dict] = {e["code"]: e for e in EXAM_CATALOG}

# Synonymes / variantes observés dans le registre papier → code canonique.
EXAM_SYNONYMS: dict[str, str] = {
    "NFS": "NFS",
    "HEMOGRAMME": "NFS",
    "NUMERATION": "NFS",
    "GE": "GE",
    "GOUTTE EPAISSE": "GE",
    "PALU": "GE",
    "PALUDISME": "GE",
    "CRP": "CRP",
    "UREE": "UREE",
    "URE": "UREE",
    "GLYCEMIE": "GLYC",
    "GLY": "GLYC",
    "GLYC": "GLYC",
    "GLU": "GLYC",
    "CREATININE": "CREAT",
    "CREAT": "CREAT",
    "CREA": "CREAT",
    "ALAT": "ALAT",
    "SGPT": "ALAT",
    "ASAT": "ASAT",
    "SGOT": "ASAT",
    "CHOLESTEROL": "CHOL",
    "CHOL": "CHOL",
    "LDL": "LDL",
    "HDL": "HDL",
    "TRIGLYCERIDES": "TG",
    "TG": "TG",
    "TRIGLYCERIDE": "TG",
    "AGHBS": "AGHBS",
    "AG HBS": "AGHBS",
    "HBS": "AGHBS",
    "HEMOGLOBINE GLYQUEE": "HBA1C",
    "HBA1C": "HBA1C",
    "HBA": "HBA1C",
    "IONOGRAMME": "IONO",
    "IONO": "IONO",
    "VS": "VS",
    "WIDAL": "WIDAL",
    "ECBU": "ECBU",
    "AST": "ASAT",
    "TGO": "ASAT",
    "ALT": "ALAT",
    "TGP": "ALAT",
    "ACIDE URIQUE": "URIC",
    "URICEMIE": "URIC",
    "CALCEMIE": "CALC",
    "CALCIUM": "CALC",
    "GROUPE RHESUS": "GRH",
    "GROUPE SANGUIN": "GRH",
    "GROUPAGE": "GRH",
    "ELECTROPHORESE HB": "ELPHB",
    "ELECTROPHORESE DE L HB": "ELPHB",
    "VIH": "HIV",
    "HIV": "HIV",
    "SEROLOGIE VIH": "HIV",
}


def resolve_exam_code(raw: str | None) -> str | None:
    """Normalise un libellé/abréviation vers un code canonique du catalogue.

    Insensible à la casse et aux accents ; renvoie None si non reconnu.
    """
    if not raw:
        return None
    import unicodedata

    key = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode().strip().upper()
    if key in EXAM_BY_CODE:
        return key
    return EXAM_SYNONYMS.get(key)

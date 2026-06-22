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


DEFAULT_PREANALYTICS = {
    "sample_type": "Sang veineux",
    "container": "Tube sec ou heparine selon automate",
    "collection_condition": "Identifier le tube, eviter hemolyse et delai inutile.",
    "transport_delay_minutes": 120,
    "bench": "Routine",
    "patient_instruction": None,
    "quality_note": "Verifier identite patient, concordance tube/code-barres et aspect du prelevement.",
}

DEFAULT_TECHNICAL_SHEET = {
    "source": "Referentiel interne RuggyLab OS, inspire des manuels techniques de laboratoire.",
    "summary": "Procedure a adapter aux reactifs, automates et modes operatoires locaux valides.",
    "key_steps": [
        "Verifier l'identite et la conformite du prelevement.",
        "Controler les reactifs, lots, dates de peremption et controles qualite requis.",
        "Saisir ou importer le resultat puis verifier les alertes critiques et coherences.",
    ],
    "qc_requirements": [
        "Controle interne selon la paillasse et la frequence definie par le laboratoire.",
    ],
    "common_rejection_reasons": [
        "Tube non conforme",
        "Identification insuffisante",
        "Delai ou conservation non conforme",
    ],
}


EXAM_WORKFLOW_METADATA: dict[str, dict] = {
    "NFS": {
        "preanalytics": {
            "sample_type": "Sang total",
            "container": "Tube EDTA violet",
            "collection_condition": "Inversions douces 8 a 10 fois; eviter coagulum.",
            "transport_delay_minutes": 120,
            "bench": "Hematologie",
        },
        "technical_sheet": {
            "summary": "Hemogramme: numeration et constantes hematologiques, avec frottis si anomalie.",
            "key_steps": [
                "Verifier tube EDTA, absence de caillot et volume suffisant.",
                "Passer les controles haut, normal et bas selon la frequence locale.",
                "Revoir frottis ou flags automate avant validation si anomalie.",
            ],
            "qc_requirements": [
                "Controle interne quotidien haut/normal/bas.",
                "Verifier concordance des flags automate avec la lecture si necessaire.",
            ],
            "common_rejection_reasons": ["Caillot", "Tube insuffisamment rempli", "Tube non EDTA"],
        },
    },
    "GE": {
        "preanalytics": {
            "sample_type": "Sang capillaire ou sang EDTA",
            "container": "Lame goutte epaisse/frottis mince ou tube EDTA violet",
            "collection_condition": "Preparer rapidement goutte epaisse et frottis mince; bien identifier les lames.",
            "transport_delay_minutes": 60,
            "bench": "Parasitologie",
        },
        "technical_sheet": {
            "summary": "Recherche du paludisme par goutte epaisse et frottis mince.",
            "key_steps": [
                "Preparer goutte epaisse et frottis mince correctement seches.",
                "Colorer selon la procedure validee de la paillasse.",
                "Lire au microscope et confirmer les resultats douteux.",
            ],
            "qc_requirements": ["Double lecture si resultat douteux ou charge elevee."],
            "common_rejection_reasons": [
                "Lame non identifiee",
                "Etalement illisible",
                "Coloration non conforme",
            ],
        },
    },
    "GLYC": {
        "preanalytics": {
            "sample_type": "Plasma/serum ou sang total selon methode",
            "container": "Tube fluorure oxalate recommande",
            "collection_condition": "Prelevement idealement a jeun 12 h; eviter effort/stress immediat.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
            "patient_instruction": "A jeun si demande de glycemie a jeun.",
        },
        "technical_sheet": {
            "summary": "Dosage du glucose par methode enzymatique ou automate de biochimie.",
            "key_steps": [
                "Confirmer le statut a jeun si pertinent.",
                "Utiliser tube fluorure oxalate si delai previsible.",
                "Verifier controle et linearite selon la methode locale.",
            ],
            "qc_requirements": ["Controle serum avant ou avec la serie."],
            "common_rejection_reasons": [
                "Delai trop long sans antiglycolytique",
                "Hemolyse importante",
            ],
        },
    },
    "CREAT": {
        "preanalytics": {
            "sample_type": "Serum, plasma heparine ou urines selon prescription",
            "container": "Tube sec ou heparine; bocal propre pour urines 24 h",
            "collection_condition": "Eviter hemolyse; preciser urines fraiches ou 24 h.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "UREE": {
        "preanalytics": {
            "sample_type": "Serum/plasma ou urines 24 h",
            "container": "Tube sec ou heparine; bocal propre pour urines 24 h",
            "collection_condition": "Prelevement propre, acheminement rapide.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "ALAT": {
        "preanalytics": {
            "sample_type": "Serum ou plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Eviter hemolyse; separer le serum/plasma rapidement si delai.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "ASAT": {
        "preanalytics": {
            "sample_type": "Serum ou plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Eviter hemolyse; separer le serum/plasma rapidement si delai.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "CRP": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine selon methode",
            "collection_condition": "Identifier et acheminer rapidement.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "IONO": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube heparine recommande selon automate",
            "collection_condition": "Eviter hemolyse et garrot prolonge.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "CHOL": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Prelevement de preference a jeun, loin des repas.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
            "patient_instruction": "A jeun si bilan lipidique complet demande.",
        },
    },
    "HDL": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Prelevement de preference a jeun, loin des repas.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
            "patient_instruction": "A jeun si bilan lipidique complet demande.",
        },
    },
    "LDL": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Prelevement de preference a jeun, loin des repas.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
            "patient_instruction": "A jeun si bilan lipidique complet demande.",
        },
    },
    "TG": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Prelevement a jeun, loin des repas.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
            "patient_instruction": "A jeun.",
        },
    },
    "HBA1C": {
        "preanalytics": {
            "sample_type": "Sang total",
            "container": "Tube EDTA violet",
            "collection_condition": "Inversions douces; pas de jeune requis.",
            "transport_delay_minutes": 240,
            "bench": "Biochimie",
        },
    },
    "BILT": {
        "preanalytics": {
            "sample_type": "Serum/plasma",
            "container": "Tube sec ou heparine",
            "collection_condition": "Proteger de la lumiere; separer rapidement.",
            "transport_delay_minutes": 120,
            "bench": "Biochimie",
        },
    },
    "ECBU": {
        "preanalytics": {
            "sample_type": "Urines",
            "container": "Flacon sterile",
            "collection_condition": "Milieu de jet apres toilette; acheminer rapidement.",
            "transport_delay_minutes": 60,
            "bench": "Microbiologie",
        },
        "technical_sheet": {
            "summary": "Examen cytobacteriologique des urines: prelevement sterile et delai court.",
            "key_steps": [
                "Verifier flacon sterile, identite et heure de prelevement.",
                "Traiter rapidement ou conserver selon procedure locale.",
                "Signaler tout delai incompatible avec la culture.",
            ],
            "qc_requirements": ["Controle des milieux et conditions d'incubation selon procedure."],
            "common_rejection_reasons": [
                "Flacon non sterile",
                "Delai excessif",
                "Volume insuffisant",
            ],
        },
    },
    "GRH": {
        "preanalytics": {
            "sample_type": "Sang total ou serum selon technique",
            "container": "Tube EDTA ou tube sec selon procedure locale",
            "collection_condition": "Identitovigilance renforcee; etiquette au lit du patient.",
            "transport_delay_minutes": 60,
            "bench": "Immuno-hematologie",
        },
        "technical_sheet": {
            "summary": "Groupage sanguin avec controle des reactions et resultats douteux.",
            "key_steps": [
                "Verifier strictement l'identite patient et tube.",
                "Executer controles positifs/negatifs requis.",
                "Repeter ou adresser tout resultat discordant.",
            ],
            "qc_requirements": ["Controle quotidien des reactifs et temoins."],
            "common_rejection_reasons": [
                "Identite douteuse",
                "Tube non conforme",
                "Discordance de controle",
            ],
        },
    },
}


def _merge_nested(default: dict, override: dict | None) -> dict:
    merged = dict(default)
    if override:
        merged.update(override)
    return merged


def exam_workflow_metadata(code: str | None) -> dict | None:
    """Retourne les consignes pre-analytiques et la fiche technique d'un examen."""
    resolved = resolve_exam_code(code)
    if resolved is None:
        return None
    raw = EXAM_WORKFLOW_METADATA.get(resolved, {})
    return {
        "preanalytics": _merge_nested(DEFAULT_PREANALYTICS, raw.get("preanalytics")),
        "technical_sheet": _merge_nested(DEFAULT_TECHNICAL_SHEET, raw.get("technical_sheet")),
    }


def exam_catalog_entry(code: str | None) -> dict | None:
    """Retourne une entrée complète du catalogue, enrichie des consignes terrain."""
    resolved = resolve_exam_code(code)
    if resolved is None:
        return None
    entry = dict(EXAM_BY_CODE[resolved])
    metadata = exam_workflow_metadata(resolved)
    if metadata:
        entry.update(metadata)
    return entry


def _enrich_catalog_entries() -> None:
    for entry in EXAM_CATALOG:
        metadata = exam_workflow_metadata(entry["code"])
        if metadata:
            entry.update(metadata)


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


_enrich_catalog_entries()

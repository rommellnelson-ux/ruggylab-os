"""Parseur du registre maître papier → données structurées.

Convertit les libellés d'examens en texte libre tels qu'ils figurent dans les
registres numérisés (« Créat 77,2 », « GE +145 trophozoïtes/champ »,
« CRP négative », « NFS 12,7 ») en enregistrements structurés exploitables.

Logique pure (aucun accès base, aucune donnée patient en dur) — destinée à
alimenter une prévisualisation d'import (dry-run) avant toute écriture.
"""

from __future__ import annotations

import re

from app.services.exam_catalog import resolve_exam_code

# Sépare une cellule multi-examens : « NFS ; Urée 0,13 ; Créat 77,2 ».
# On ne coupe que sur ';' / retour-ligne : '/' apparaît dans des unités
# (« trophozoïtes/champ ») et ne doit pas être traité comme séparateur.
_SPLIT_RE = re.compile(r"[;\n]+")
# Premier nombre signé, décimale française (virgule) ou anglaise (point)
_NUM_RE = re.compile(r"[+\-]?\d+(?:[.,]\d+)?")
# Partie « nom d'examen » en tête : lettres/espaces/accents avant tout chiffre/marqueur
_NAME_RE = re.compile(r"^[^\d+\-:=≈]+")


def split_exams(cell: str | None) -> list[str]:
    """Découpe une cellule d'examens multiples en tokens individuels."""
    if not cell:
        return []
    return [t.strip() for t in _SPLIT_RE.split(cell) if t and t.strip()]


def _parse_number(text: str) -> float | None:
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _qualitative(text: str) -> str | None:
    low = text.lower()
    if "négati" in low or "negati" in low:
        return "negative"
    if "positi" in low or "+" in text:
        return "positive"
    return None


def parse_exam_token(raw: str | None) -> dict:
    """Structure un token d'examen unique.

    Retourne ``{raw, exam_code, name, numeric_value, qualitative, recognized}``.
    ``exam_code`` est None si l'examen n'est pas reconnu dans le catalogue.
    """
    raw = (raw or "").strip()
    if not raw:
        return {
            "raw": "",
            "exam_code": None,
            "name": "",
            "numeric_value": None,
            "qualitative": None,
            "recognized": False,
        }

    name_match = _NAME_RE.match(raw)
    name_part = name_match.group(0).strip() if name_match else raw
    rest = raw[len(name_part) :] if name_match else ""

    # Résolution : nom complet, puis repli sur le premier mot (gère les suffixes
    # qualitatifs comme « CRP négative » → code CRP).
    exam_code = resolve_exam_code(name_part)
    if exam_code is None and " " in name_part:
        exam_code = resolve_exam_code(name_part.split()[0])
    return {
        "raw": raw,
        "exam_code": exam_code,
        "name": name_part,
        "numeric_value": _parse_number(rest if rest else raw),
        "qualitative": _qualitative(raw),
        "recognized": exam_code is not None,
    }


def parse_exam_cell(cell: str | None) -> list[dict]:
    """Parse une cellule entière (possiblement multi-examens)."""
    return [parse_exam_token(tok) for tok in split_exams(cell)]


def build_import_preview(rows: list[dict]) -> dict:
    """Prévisualisation d'import (dry-run, sans écriture base).

    Chaque ``row`` est un dict aux clés souples :
    ``nom`` (ou ``patient``), ``date``, ``examens`` (texte), ``montant``,
    ``part_cmu``, ``type_registre``, ``prescripteur``, ``provenance``.

    Retourne un récapitulatif : nb dossiers, nb examens, examens reconnus /
    non reconnus, montant total, et la liste structurée prête à importer.
    """
    preview: list[dict] = []
    total_exams = 0
    recognized = 0
    unrecognized_labels: dict[str, int] = {}
    total_amount = 0.0

    for idx, row in enumerate(rows, start=1):
        name = (row.get("nom") or row.get("patient") or row.get("nom_patient") or "").strip()
        exams = parse_exam_cell(row.get("examens") or row.get("Examens"))
        total_exams += len(exams)
        for e in exams:
            if e["recognized"]:
                recognized += 1
            elif e["name"]:
                key = e["name"].upper()[:24]
                unrecognized_labels[key] = unrecognized_labels.get(key, 0) + 1
        amount = row.get("montant") or row.get("montant_total_fcfa") or row.get("Montant_FCFA")
        if isinstance(amount, (int, float)):
            total_amount += amount
        preview.append(
            {
                "row": idx,
                "patient_name": name,
                "date": row.get("date") or row.get("date_demande"),
                "type_registre": row.get("type_registre") or row.get("Type_Registre"),
                "prescripteur": row.get("prescripteur") or row.get("Prescripteur"),
                "amount_fcfa": amount if isinstance(amount, (int, float)) else None,
                "exams": exams,
                "warnings": [] if name else ["nom patient manquant"],
            }
        )

    return {
        "total_rows": len(rows),
        "total_exams": total_exams,
        "recognized_exams": recognized,
        "unrecognized_exams": total_exams - recognized,
        "recognition_rate_pct": round(recognized / total_exams * 100, 1) if total_exams else 0.0,
        "top_unrecognized": sorted(unrecognized_labels.items(), key=lambda kv: kv[1], reverse=True)[
            :15
        ],
        "total_amount_fcfa": total_amount,
        "rows": preview,
    }

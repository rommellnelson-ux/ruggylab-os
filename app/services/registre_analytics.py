"""Analyse rétrospective du registre maître (volumes, recettes, épidémiologie).

Calcule des indicateurs agrégés à partir des lignes du registre (postées en
JSON) sans rien persister : volumétrie, recettes et part CMU, top examens,
positivité paludisme (goutte épaisse), répartition mensuelle, prescripteurs.
Logique pure — aucun accès base, aucune donnée patient conservée.
"""

from __future__ import annotations

import collections
import datetime as dt

from app.services.registre_parser import parse_exam_cell

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d")


def _parse_date(value) -> dt.date | None:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.date() if isinstance(value, dt.datetime) else value
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _amount(row: dict, *keys: str) -> float:
    for k in keys:
        v = row.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def compute_registre_analytics(rows: list[dict]) -> dict:
    """Indicateurs rétrospectifs sur les lignes du registre."""
    total = len(rows)
    by_type: collections.Counter = collections.Counter()
    revenue_total = 0.0
    cmu_total = 0.0
    by_month: dict[str, dict] = {}
    exam_counter: collections.Counter = collections.Counter()
    prescripteurs: collections.Counter = collections.Counter()
    provenances: collections.Counter = collections.Counter()
    malaria_tested = 0
    malaria_positive = 0
    dated = 0

    for row in rows:
        rtype = (row.get("type_registre") or row.get("Type_Registre") or "Inconnu").strip()
        by_type[rtype] += 1

        amount = _amount(row, "montant", "montant_total_fcfa", "Montant_FCFA")
        cmu = _amount(row, "part_cmu", "part_cmu_fcfa", "Part_CMU_FCFA")
        revenue_total += amount
        cmu_total += cmu

        presc = (row.get("prescripteur") or row.get("Prescripteur") or "").strip()
        if presc:
            prescripteurs[presc] += 1
        prov = (row.get("provenance") or row.get("Provenance") or "").strip()
        if prov:
            provenances[prov] += 1

        d = _parse_date(row.get("date") or row.get("date_demande") or row.get("Date"))
        if d:
            dated += 1
            mkey = f"{d.year:04d}-{d.month:02d}"
            bucket = by_month.setdefault(mkey, {"count": 0, "revenue_fcfa": 0.0})
            bucket["count"] += 1
            bucket["revenue_fcfa"] += amount

        for token in parse_exam_cell(row.get("examens") or row.get("Examens")):
            label = token["exam_code"] or (token["name"].upper()[:24] if token["name"] else "?")
            exam_counter[label] += 1
            if token["exam_code"] == "GE":
                malaria_tested += 1
                if token["qualitative"] == "positive":
                    malaria_positive += 1

    months = [{"month": m, **vals} for m, vals in sorted(by_month.items())]
    malaria_rate = round(malaria_positive / malaria_tested * 100, 1) if malaria_tested else 0.0

    return {
        "total_dossiers": total,
        "dated_dossiers": dated,
        "by_type": dict(by_type),
        "revenue_total_fcfa": round(revenue_total, 2),
        "cmu_part_fcfa": round(cmu_total, 2),
        "cmu_share_pct": round(cmu_total / revenue_total * 100, 1) if revenue_total else 0.0,
        "top_exams": exam_counter.most_common(15),
        "top_prescripteurs": prescripteurs.most_common(10),
        "top_provenances": provenances.most_common(10),
        "malaria_tested": malaria_tested,
        "malaria_positive": malaria_positive,
        "malaria_positivity_pct": malaria_rate,
        "by_month": months,
    }

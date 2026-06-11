"""Construction du dossier patient complet : timeline des résultats + tendances.

Agrège tous les échantillons et résultats d'un patient, calcule des séries
temporelles par analyte (pour les sparklines), et produit un Bundle FHIR R4
regroupant un DiagnosticReport par résultat.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Patient, Result, Sample
from app.services.fhir_builder import build_diagnostic_report


def _extract_numeric(raw: object) -> float | None:
    """Extrait une valeur numérique depuis un data_point (nombre brut ou dict{value})."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, dict):
        val = raw.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
    return None


def build_patient_history(db: Session, patient: Patient) -> dict:
    """Retourne le dossier complet : démographie, timeline de résultats, tendances.

    - ``timeline`` : liste de résultats (les plus récents d'abord) avec statut.
    - ``trends`` : { analyte: [{date, value}] } trié chronologiquement (ancien→récent),
      utilisable directement pour tracer des sparklines.
    """
    samples = (
        db.query(Sample).filter(Sample.patient_id == patient.id).order_by(Sample.id.asc()).all()
    )
    sample_ids = [s.id for s in samples]
    barcode_by_sample = {s.id: s.barcode for s in samples}

    results: list[Result] = []
    if sample_ids:
        results = (
            db.query(Result)
            .filter(Result.sample_id.in_(sample_ids))
            .order_by(Result.analysis_date.asc(), Result.id.asc())
            .all()
        )

    # Tendances par analyte (ordre chronologique ancien→récent)
    trends: dict[str, list[dict]] = {}
    for r in results:
        date_iso = r.analysis_date.isoformat() if r.analysis_date else None
        for analyte, raw in (r.data_points or {}).items():
            value = _extract_numeric(raw)
            if value is None:
                continue
            trends.setdefault(analyte, []).append({"date": date_iso, "value": value})

    # Timeline (récent→ancien pour affichage)
    timeline = []
    for r in sorted(results, key=lambda x: (x.analysis_date or x.id, x.id), reverse=True):
        timeline.append(
            {
                "result_id": r.id,
                "sample_id": r.sample_id,
                "sample_barcode": barcode_by_sample.get(r.sample_id),
                "analysis_date": r.analysis_date.isoformat() if r.analysis_date else None,
                "is_critical": r.is_critical,
                "is_validated": r.is_validated,
                "is_auto_validated": r.is_auto_validated,
                "delta_exceeded": r.delta_exceeded,
                "flags": r.flags,
                "data_points": r.data_points,
            }
        )

    return {
        "patient": {
            "id": patient.id,
            "ipp_unique_id": patient.ipp_unique_id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
            "sex": patient.sex,
            "rank": patient.rank,
        },
        "sample_count": len(samples),
        "result_count": len(results),
        "critical_count": sum(1 for r in results if r.is_critical),
        "timeline": timeline,
        "trends": trends,
    }


def build_patient_fhir_bundle(db: Session, patient: Patient) -> dict:
    """Bundle FHIR R4 (type ``collection``) regroupant un DiagnosticReport par résultat."""
    samples = db.query(Sample).filter(Sample.patient_id == patient.id).all()
    sample_ids = [s.id for s in samples]
    results: list[Result] = []
    if sample_ids:
        results = (
            db.query(Result)
            .filter(Result.sample_id.in_(sample_ids))
            .order_by(Result.analysis_date.asc(), Result.id.asc())
            .all()
        )

    entries = []
    for r in results:
        report = build_diagnostic_report(r)
        entries.append(
            {
                "fullUrl": f"urn:ruggylab:result:{r.id}",
                "resource": report.model_dump(exclude_none=True),
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(entries),
        "entry": entries,
        "_patient_ipp": patient.ipp_unique_id,
    }

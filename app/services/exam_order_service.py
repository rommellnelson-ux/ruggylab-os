"""Service — suivi du « fil » d'une prescription d'examens.

Le fil relie : bon de prescription → échantillon prélevé → résultats par examen.
``sync_order_progress`` rapproche les résultats de l'échantillon rattaché avec
les examens demandés et met à jour les statuts (item + bon) de façon idempotente.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ExamOrder, Patient, Result, Sample
from app.schemas.exam_order import ExamOrderThread, ExamThreadStep
from app.services.exam_catalog import exam_catalog_entry


def _patient_label(patient: Patient | None) -> str | None:
    if patient is None:
        return None
    name = f"{patient.last_name} {patient.first_name}".strip()
    return f"{name} ({patient.ipp_unique_id})" if name else patient.ipp_unique_id


def sync_order_progress(db: Session, order: ExamOrder) -> ExamOrder:
    """Met à jour les statuts du bon à partir des résultats de l'échantillon.

    - chaque examen demandé est marqué ``resulted`` (+ result_id) si un résultat
      portant le même ``exam_code`` existe sur l'échantillon rattaché ;
    - le statut du bon est dérivé : prescribed → collected → in_progress →
      completed (les bons ``cancelled`` ne sont jamais réécrits).
    """
    if order.status == "cancelled":
        return order

    results_by_code: dict[str, Result] = {}
    if order.sample_id is not None:
        results = db.query(Result).filter(Result.sample_id == order.sample_id).all()
        for res in results:
            if res.exam_code:
                # On garde le résultat le plus récent par code d'examen.
                prev = results_by_code.get(res.exam_code)
                if prev is None or res.analysis_date >= prev.analysis_date:
                    results_by_code[res.exam_code] = res

    resulted = 0
    for item in order.items:
        if item.status == "cancelled":
            continue
        match = results_by_code.get(item.exam_code)
        if match is not None:
            item.status = "resulted"
            item.result_id = match.id
            resulted += 1
        else:
            item.status = "pending"
            item.result_id = None

    active_items = [it for it in order.items if it.status != "cancelled"]
    if active_items and resulted == len(active_items):
        order.status = "completed"
    elif resulted > 0:
        order.status = "in_progress"
    elif order.sample_id is not None:
        order.status = "collected"
    else:
        order.status = "prescribed"

    db.commit()
    db.refresh(order)
    return order


def build_thread(
    db: Session,
    order: ExamOrder,
    *,
    synchronize: bool = True,
) -> ExamOrderThread:
    """Construit la vue « fil » consolidée pour la paillasse."""
    if synchronize:
        sync_order_progress(db, order)

    patient = db.query(Patient).filter(Patient.id == order.patient_id).first()
    sample: Sample | None = None
    if order.sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == order.sample_id).first()

    # Résultats indexés pour enrichir chaque étape (critique / validé) et,
    # sans synchronisation, projeter un fil à jour sans modifier la session.
    results_by_id: dict[int, Result] = {}
    results_by_code: dict[str, Result] = {}
    if order.sample_id is not None:
        for r in db.query(Result).filter(Result.sample_id == order.sample_id).all():
            results_by_id[r.id] = r
            if r.exam_code:
                previous = results_by_code.get(r.exam_code)
                if previous is None or r.analysis_date >= previous.analysis_date:
                    results_by_code[r.exam_code] = r

    steps: list[ExamThreadStep] = []
    resulted = 0
    active = 0
    for item in order.items:
        item_status = item.status
        item_result_id = item.result_id
        if not synchronize and item_status != "cancelled":
            match = results_by_code.get(item.exam_code)
            item_status = "resulted" if match is not None else "pending"
            item_result_id = match.id if match is not None else None
        if item_status != "cancelled":
            active += 1
        if item_status == "resulted":
            resulted += 1
        res: Result | None = results_by_id.get(item_result_id) if item_result_id else None
        catalog = exam_catalog_entry(item.exam_code)
        steps.append(
            ExamThreadStep(
                exam_code=item.exam_code,
                exam_label=item.exam_label,
                status=item_status,
                result_id=item_result_id,
                is_critical=bool(res.is_critical) if res else False,
                is_validated=bool(res.is_validated) if res else False,
                preanalytics=catalog.get("preanalytics") if catalog else None,
                technical_sheet=catalog.get("technical_sheet") if catalog else None,
            )
        )

    progress = round(100 * resulted / active) if active else 0
    projected_status = order.status
    if not synchronize and order.status != "cancelled":
        if active and resulted == active:
            projected_status = "completed"
        elif resulted > 0:
            projected_status = "in_progress"
        elif order.sample_id is not None:
            projected_status = "collected"
        else:
            projected_status = "prescribed"
    return ExamOrderThread(
        order_id=order.id,
        status=projected_status,
        priority=order.priority,
        patient_id=order.patient_id,
        patient_label=_patient_label(patient),
        prescriber=order.prescriber,
        ordered_at=order.ordered_at,
        sample_id=order.sample_id,
        sample_barcode=sample.barcode if sample else None,
        sample_status=sample.status if sample else None,
        total_exams=active,
        resulted_exams=resulted,
        progress_pct=progress,
        steps=steps,
    )

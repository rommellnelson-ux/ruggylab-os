"""Préparation serveur de la Vue Paillasse.

La page paillasse ne doit pas embarquer tout le cockpit puis filtrer côté JS :
ce service expose uniquement les alertes et files d'action utiles à l'agent.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import Patient, Result, Sample, TatTarget, User
from app.services.patient_access import apply_result_patient_scope
from app.utils.datetime_utils import utcnow_naive

_NON_ANALYTIC_KEYS = {"manual_entry_by", "entry_timestamp", "calibration", "overall_flags"}


def _analytes(data_points: dict[str, Any] | None) -> list[str]:
    if not data_points:
        return []
    return sorted(k for k in data_points if isinstance(k, str) and k not in _NON_ANALYTIC_KEYS)


def _patient_context(patient: Patient | None) -> dict | None:
    if patient is None:
        return None
    name = f"{patient.last_name} {patient.first_name}".strip()
    return {
        "id": patient.id,
        "ipp": patient.ipp_unique_id,
        "display_name": name or None,
        "unit": patient.unit,
    }


def _sample_context(sample: Sample) -> dict:
    return {"id": sample.id, "barcode": sample.barcode, "status": sample.status}


def _targets_by_code(db: Session) -> dict[str, TatTarget]:
    rows = db.query(TatTarget).filter(TatTarget.is_active.is_(True)).all()
    return {target.exam_code: target for target in rows}


def _base_result_query(db: Session, current_user: User) -> Any:
    query = db.query(Result).options(joinedload(Result.sample).joinedload(Sample.patient))
    return apply_result_patient_scope(query, current_user)


def list_pending_critical_values(db: Session, current_user: User, *, limit: int = 12) -> list[dict]:
    results = (
        _base_result_query(db, current_user)
        .filter(Result.is_critical.is_(True), Result.critical_ack_at.is_(None))
        .order_by(Result.analysis_date.desc(), Result.id.desc())
        .limit(limit)
        .all()
    )
    items: list[dict] = []
    for result in results:
        items.append(
            {
                "result_id": result.id,
                "exam_code": result.exam_code,
                "analysis_date": result.analysis_date,
                "patient": _patient_context(result.sample.patient if result.sample else None),
                "sample": _sample_context(result.sample),
                "analytes": _analytes(result.data_points),
                "message": "Valeur critique à prendre en charge",
            }
        )
    return items


def list_tat_expiring_soon(
    db: Session,
    current_user: User,
    *,
    window_minutes: int = 15,
    limit: int = 20,
) -> list[dict]:
    now = utcnow_naive()
    targets = _targets_by_code(db)
    candidates = (
        _base_result_query(db, current_user)
        .filter(
            Result.bio_validated_at.is_(None),
            Result.registered_at.isnot(None),
            Result.exam_code.isnot(None),
        )
        .order_by(Result.registered_at.asc(), Result.id.asc())
        .limit(limit * 4)
        .all()
    )

    items: list[dict] = []
    for result in candidates:
        if result.exam_code is None or result.registered_at is None:
            continue
        target = targets.get(result.exam_code)
        if target is None:
            continue
        elapsed = round((now - result.registered_at).total_seconds() / 60.0, 1)
        remaining = round(float(target.target_minutes) - elapsed, 1)
        if remaining < 0 or remaining > window_minutes:
            continue
        due_at = result.registered_at + dt.timedelta(minutes=target.target_minutes)
        items.append(
            {
                "result_id": result.id,
                "exam_code": result.exam_code,
                "target_minutes": target.target_minutes,
                "elapsed_minutes": elapsed,
                "remaining_minutes": remaining,
                "due_at": due_at,
                "patient": _patient_context(result.sample.patient if result.sample else None),
                "sample": _sample_context(result.sample),
            }
        )
        if len(items) >= limit:
            break
    return sorted(items, key=lambda item: item["remaining_minutes"])


def list_routine_validation_queue(
    db: Session, current_user: User, *, limit: int = 40
) -> list[dict]:
    now = utcnow_naive()
    targets = _targets_by_code(db)
    results = (
        _base_result_query(db, current_user)
        .filter(
            Result.is_critical.is_(False),
            Result.delta_exceeded.is_(False),
            Result.bio_validated_at.is_(None),
        )
        .order_by(Result.analysis_date.asc(), Result.id.asc())
        .limit(limit * 3)
        .all()
    )
    items: list[dict] = []
    for result in results:
        if result.exam_code and result.registered_at:
            target = targets.get(result.exam_code)
            if target:
                elapsed = (now - result.registered_at).total_seconds() / 60.0
                remaining = float(target.target_minutes) - elapsed
                if 0 <= remaining <= 15:
                    continue
        items.append(
            {
                "result_id": result.id,
                "exam_code": result.exam_code,
                "analysis_date": result.analysis_date,
                "patient": _patient_context(result.sample.patient if result.sample else None),
                "sample": _sample_context(result.sample),
                "analytes": _analytes(result.data_points),
            }
        )
        if len(items) >= limit:
            break
    return items


def build_bench_radar(db: Session, current_user: User) -> dict:
    return {
        "generated_at": utcnow_naive(),
        "criticals": list_pending_critical_values(db, current_user),
        "tat_expiring": list_tat_expiring_soon(db, current_user),
        "routine": list_routine_validation_queue(db, current_user),
    }

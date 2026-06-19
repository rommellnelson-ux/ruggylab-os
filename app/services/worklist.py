"""File de travail opérationnelle pour agents de laboratoire."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models import NonConformity, Patient, QcControl, QcResult, Result, Sample, TatTarget, User
from app.models.ruggylab_os import UserRole
from app.schemas.qc import QC_REJECT_RULES
from app.schemas.worklist import WorklistAction, WorklistItem, WorklistResponse, WorklistSummary
from app.services.patient_access import apply_result_patient_scope
from app.utils.datetime_utils import utcnow_naive


def _is_unrestricted(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.OFFICER) or user.unit is None


def _sample_scope(query: Any, user: User) -> Any:
    if _is_unrestricted(user):
        return query
    return query.outerjoin(Patient, Sample.patient_id == Patient.id).filter(
        or_(Patient.id.is_(None), Patient.unit.is_(None), Patient.unit == user.unit)
    )


def _priority_rank(priority: str) -> int:
    return {"critical": 0, "overdue": 1, "urgent": 2, "blocked": 3, "normal": 4}.get(priority, 9)


def _patient_label(sample: Sample | None) -> str:
    if sample is None or sample.patient is None:
        return "patient non rattaché"
    return (
        f"{sample.patient.last_name} {sample.patient.first_name} · {sample.patient.ipp_unique_id}"
    )


def _targets_by_code(db: Session) -> dict[str, TatTarget]:
    return {t.exam_code: t for t in db.query(TatTarget).filter(TatTarget.is_active.is_(True)).all()}


def _critical_items(db: Session, user: User, limit: int) -> list[WorklistItem]:
    now = utcnow_naive()
    query = db.query(Result).options(joinedload(Result.sample).joinedload(Sample.patient))
    query = apply_result_patient_scope(query, user)
    rows = (
        query.filter(Result.is_critical.is_(True), Result.critical_ack_at.is_(None))
        .order_by(Result.analysis_date.asc(), Result.id.asc())
        .limit(limit)
        .all()
    )
    items: list[WorklistItem] = []
    for result in rows:
        elapsed = (
            int((now - result.analysis_date).total_seconds() / 60) if result.analysis_date else 0
        )
        sample = result.sample
        title = f"Valeur critique · {result.exam_code or 'résultat'}"
        subtitle = f"{sample.barcode if sample else 'échantillon ?'} · {_patient_label(sample)}"
        items.append(
            WorklistItem(
                id=f"critical:{result.id}",
                category="critical",
                priority="critical" if elapsed >= 30 else "urgent",
                title=title,
                subtitle=subtitle,
                status="non prise en charge",
                elapsed_minutes=elapsed,
                unit=sample.patient.unit if sample and sample.patient else None,
                actions=[
                    WorklistAction(
                        label="Prendre en charge",
                        method="PATCH",
                        path=f"/api/v1/results/{result.id}/ack-critical",
                        style="danger",
                    ),
                    WorklistAction(label="Ouvrir", path=f"#/results?result={result.id}"),
                ],
            )
        )
    return items


def _tat_items(db: Session, user: User, limit: int) -> list[WorklistItem]:
    now = utcnow_naive()
    targets = _targets_by_code(db)
    query = db.query(Result).options(joinedload(Result.sample).joinedload(Sample.patient))
    query = apply_result_patient_scope(query, user)
    rows = (
        query.filter(
            Result.bio_validated_at.is_(None),
            Result.registered_at.isnot(None),
            Result.exam_code.isnot(None),
        )
        .order_by(Result.registered_at.asc(), Result.id.asc())
        .limit(limit * 3)
        .all()
    )
    items: list[WorklistItem] = []
    for result in rows:
        if result.exam_code is None or result.registered_at is None:
            continue
        target = targets.get(result.exam_code)
        if target is None:
            continue
        due_at = result.registered_at + dt.timedelta(minutes=target.target_minutes)
        remaining = int((due_at - now).total_seconds() / 60)
        if remaining > 15:
            continue
        priority = "overdue" if remaining < 0 else "urgent"
        sample = result.sample
        items.append(
            WorklistItem(
                id=f"tat:{result.id}",
                category="tat",
                priority=priority,
                title=f"TAT {'dépassé' if remaining < 0 else 'à échéance'} · {result.exam_code}",
                subtitle=f"{sample.barcode if sample else 'échantillon ?'} · reste {remaining} min",
                status="hors délai" if remaining < 0 else "moins de 15 min",
                due_at=due_at,
                unit=sample.patient.unit if sample and sample.patient else None,
                actions=[
                    WorklistAction(label="Ouvrir résultat", path=f"#/results?result={result.id}")
                ],
            )
        )
        if len(items) >= limit:
            break
    return items


def _sample_items(db: Session, user: User, limit: int) -> list[WorklistItem]:
    query = db.query(Sample).options(joinedload(Sample.patient))
    query = _sample_scope(query, user)
    rows = (
        query.filter(Sample.status.in_(["Recu", "En cours", "Annule"]))
        .order_by(Sample.collection_date.asc(), Sample.id.asc())
        .limit(limit)
        .all()
    )
    items: list[WorklistItem] = []
    for sample in rows:
        blocked = sample.status == "Annule"
        items.append(
            WorklistItem(
                id=f"sample:{sample.id}",
                category="sample",
                priority="blocked" if blocked else "normal",
                title=f"Échantillon {sample.status or 'à suivre'}",
                subtitle=f"{sample.barcode} · {_patient_label(sample)}",
                status=sample.status or "inconnu",
                unit=sample.patient.unit if sample.patient else None,
                actions=[WorklistAction(label="Ouvrir échantillons", path="#/samples")],
            )
        )
    return items


def _qc_items(db: Session, limit: int) -> list[WorklistItem]:
    controls = db.query(QcControl).filter(QcControl.is_active.is_(True)).all()
    latest_results: dict[int, QcResult] = {}
    control_ids = [control.id for control in controls]
    if control_ids:
        for result in (
            db.query(QcResult)
            .filter(QcResult.control_id.in_(control_ids))
            .order_by(QcResult.control_id.asc(), QcResult.measured_at.desc(), QcResult.id.desc())
            .all()
        ):
            latest_results.setdefault(result.control_id, result)

    items: list[WorklistItem] = []
    for control in controls:
        last = latest_results.get(control.id)
        if last is None:
            continue
        try:
            violations = json.loads(last.violations or "[]")
        except json.JSONDecodeError:
            violations = []
        if not isinstance(violations, list):
            violations = []
        rejects = [v for v in violations if v in QC_REJECT_RULES]
        if not rejects:
            continue
        items.append(
            WorklistItem(
                id=f"qc:{last.id}",
                category="qc",
                priority="urgent",
                title=f"QC à refaire · {control.analyte}",
                subtitle=f"{control.level} · violations {', '.join(rejects)}",
                status="rejet Westgard",
                actions=[
                    WorklistAction(label="Ouvrir QC", path="#/qc"),
                    WorklistAction(label="Créer NC", path="#/quality"),
                ],
            )
        )
        if len(items) >= limit:
            break
    return items


def _nc_items(db: Session, limit: int) -> list[WorklistItem]:
    now = utcnow_naive()
    rows = (
        db.query(NonConformity)
        .filter(NonConformity.status != "closed")
        .order_by(NonConformity.due_date.asc().nullslast(), NonConformity.id.desc())
        .limit(limit)
        .all()
    )
    items: list[WorklistItem] = []
    for nc in rows:
        overdue = nc.due_date is not None and nc.due_date < now
        priority = "overdue" if overdue else "urgent" if nc.severity == "critical" else "normal"
        items.append(
            WorklistItem(
                id=f"nc:{nc.id}",
                category="quality",
                priority=priority,
                title=f"NC/CAPA · {nc.title}",
                subtitle=f"{nc.severity} · {nc.source}",
                status="en retard" if overdue else nc.status,
                due_at=nc.due_date,
                actions=[WorklistAction(label="Ouvrir qualité", path="#/quality")],
            )
        )
    return items


def build_my_worklist(
    db: Session, user: User, *, limit: int = 60, category: str | None = None
) -> WorklistResponse:
    builders = {
        "critical": lambda: _critical_items(db, user, limit),
        "tat": lambda: _tat_items(db, user, limit),
        "sample": lambda: _sample_items(db, user, limit),
        "qc": lambda: _qc_items(db, limit),
        "quality": lambda: _nc_items(db, limit),
    }
    selected = [category] if category in builders else list(builders)
    items: list[WorklistItem] = []
    for key in selected:
        items.extend(builders[key]())
    items.sort(
        key=lambda item: (_priority_rank(item.priority), item.due_at or dt.datetime.max, item.id)
    )
    items = items[:limit]
    summary = WorklistSummary(
        total=len(items),
        critical=sum(1 for item in items if item.priority == "critical"),
        overdue=sum(1 for item in items if item.priority == "overdue"),
        urgent=sum(1 for item in items if item.priority == "urgent"),
        blocked=sum(1 for item in items if item.priority == "blocked"),
    )
    return WorklistResponse(generated_at=utcnow_naive(), summary=summary, items=items)

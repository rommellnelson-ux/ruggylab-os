"""Module qualité — non-conformités (NC) et actions correctives/préventives (CAPA).

ISO 15189 §4.9 (NC) / §4.10 (CAPA). Déclaration ouverte à tout agent ; les
transitions de workflow et la gestion des actions sont réservées aux officiers.
Chaque transition de statut est journalisée (audit).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import CorrectiveAction, NonConformity, User
from app.schemas.quality import (
    CorrectiveActionCreate,
    CorrectiveActionRead,
    CorrectiveActionUpdate,
    NonConformityCreate,
    NonConformityRead,
    NonConformityTransition,
)
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/quality")

# Transitions de workflow autorisées (un statut → ensemble des suivants permis).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"analysis", "closed"},
    "analysis": {"action", "open", "closed"},
    "action": {"verification", "analysis", "closed"},
    "verification": {"closed", "action"},
    "closed": set(),  # terminal
}


def _get_nc_or_404(db: Session, nc_id: int) -> NonConformity:
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Non-conformité introuvable.")
    return nc


@router.get("/non-conformities", response_model=list[NonConformityRead])
def list_non_conformities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
) -> list[NonConformity]:
    del current_user
    query = db.query(NonConformity)
    if status_filter:
        query = query.filter(NonConformity.status == status_filter)
    if severity:
        query = query.filter(NonConformity.severity == severity)
    return query.order_by(NonConformity.id.desc()).all()


@router.get("/dashboard")
def quality_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Synthèse : NC ouvertes, en retard, répartition par sévérité et statut."""
    del current_user
    now = utcnow_naive()
    total = db.query(func.count(NonConformity.id)).scalar() or 0
    open_count = (
        db.query(func.count(NonConformity.id))
        .filter(NonConformity.status != "closed")
        .scalar()
        or 0
    )
    overdue = (
        db.query(func.count(NonConformity.id))
        .filter(
            NonConformity.status != "closed",
            NonConformity.due_date.is_not(None),
            NonConformity.due_date < now,
        )
        .scalar()
        or 0
    )
    by_severity = {
        sev: (
            db.query(func.count(NonConformity.id))
            .filter(NonConformity.severity == sev, NonConformity.status != "closed")
            .scalar()
            or 0
        )
        for sev in ("minor", "major", "critical")
    }
    by_status = {
        st: (
            db.query(func.count(NonConformity.id))
            .filter(NonConformity.status == st)
            .scalar()
            or 0
        )
        for st in ("open", "analysis", "action", "verification", "closed")
    }
    return {
        "total": total,
        "open_count": open_count,
        "overdue_count": overdue,
        "by_severity": by_severity,
        "by_status": by_status,
    }


@router.get("/non-conformities/{nc_id}", response_model=NonConformityRead)
def get_non_conformity(
    nc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NonConformity:
    del current_user
    return _get_nc_or_404(db, nc_id)


@router.post(
    "/non-conformities",
    response_model=NonConformityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_non_conformity(
    payload: NonConformityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NonConformity:
    """Déclare une non-conformité (ouverte à tout agent actif)."""
    nc = NonConformity(
        **payload.model_dump(),
        detected_by_id=current_user.id,
        status="open",
    )
    db.add(nc)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="quality.nc.create",
        entity_type="non_conformity",
        entity_id=str(nc.id),
        payload={"title": nc.title, "severity": nc.severity, "source": nc.source},
    )
    db.commit()
    db.refresh(nc)
    return nc


@router.post("/non-conformities/{nc_id}/transition", response_model=NonConformityRead)
def transition_non_conformity(
    nc_id: int,
    payload: NonConformityTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> NonConformity:
    """Fait évoluer le statut d'une NC selon le workflow (réservé officier)."""
    nc = _get_nc_or_404(db, nc_id)
    old_status = nc.status
    target = payload.status
    if target == old_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La non-conformité est déjà au statut « {target} ».",
        )
    if target not in _ALLOWED_TRANSITIONS.get(old_status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transition non autorisée : {old_status} → {target}.",
        )
    nc.status = target
    if payload.root_cause is not None:
        nc.root_cause = payload.root_cause
    if target == "closed":
        nc.closed_at = utcnow_naive()
    log_audit_event(
        db,
        user=current_user,
        event_type="quality.nc.transition",
        entity_type="non_conformity",
        entity_id=str(nc.id),
        payload={"from": old_status, "to": target},
    )
    db.commit()
    db.refresh(nc)
    return nc


@router.post(
    "/non-conformities/{nc_id}/actions",
    response_model=CorrectiveActionRead,
    status_code=status.HTTP_201_CREATED,
)
def add_corrective_action(
    nc_id: int,
    payload: CorrectiveActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> CorrectiveAction:
    """Ajoute une action corrective/préventive à une NC (réservé officier)."""
    nc = _get_nc_or_404(db, nc_id)
    action = CorrectiveAction(non_conformity_id=nc.id, **payload.model_dump())
    db.add(action)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="quality.capa.create",
        entity_type="corrective_action",
        entity_id=str(action.id),
        payload={"nc_id": nc.id, "action_type": action.action_type},
    )
    db.commit()
    db.refresh(action)
    return action


@router.patch("/actions/{action_id}", response_model=CorrectiveActionRead)
def update_corrective_action(
    action_id: int,
    payload: CorrectiveActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> CorrectiveAction:
    """Met à jour le statut / l'efficacité d'une action (réservé officier)."""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action introuvable.")
    data = payload.model_dump(exclude_none=True)
    if "status" in data:
        action.status = data["status"]
        if data["status"] == "done" and action.completed_at is None:
            action.completed_at = utcnow_naive()
    if "effectiveness_checked" in data:
        action.effectiveness_checked = data["effectiveness_checked"]
    if "effectiveness_notes" in data:
        action.effectiveness_notes = data["effectiveness_notes"]
    db.commit()
    db.refresh(action)
    return action

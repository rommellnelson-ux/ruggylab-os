"""API — Registre des Accidents d'Exposition au Sang (AES).

Déclaration ouverte à tout agent authentifié (la victime déclare) ; consultation
et suivi réservés à l'encadrement (``require_officer``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.aes import AesIncident
from app.schemas.aes import AES_STATUSES, EXPOSURE_TYPES, AesCreate, AesRead, AesUpdate
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/aes")


def _get_or_404(db: Session, aes_id: int) -> AesIncident:
    incident = db.query(AesIncident).filter(AesIncident.id == aes_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Déclaration AES introuvable."
        )
    return incident


@router.post("", response_model=AesRead, status_code=status.HTTP_201_CREATED)
def declare_aes(
    payload: AesCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AesIncident:
    """Déclare un accident d'exposition au sang (tout agent authentifié)."""
    if payload.exposure_type not in EXPOSURE_TYPES:
        raise HTTPException(
            status_code=422, detail=f"Type d'exposition invalide : {payload.exposure_type}."
        )
    incident = AesIncident(
        **payload.model_dump(),
        declared_by_id=current_user.id,
        status="declared",
    )
    db.add(incident)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="aes.declare",
        entity_type="aes_incident",
        entity_id=str(incident.id),
        payload={
            "exposure_type": incident.exposure_type,
            "occurred_at": incident.occurred_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(incident)
    return incident


@router.get("", response_model=list[AesRead])
def list_aes(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> list[AesIncident]:
    """Liste les déclarations AES (encadrement)."""
    del current_user
    query = db.query(AesIncident)
    if status_filter:
        query = query.filter(AesIncident.status == status_filter)
    return query.order_by(AesIncident.id.desc()).all()


@router.get("/{aes_id}", response_model=AesRead)
def get_aes(
    aes_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> AesIncident:
    del current_user
    return _get_or_404(db, aes_id)


@router.patch("/{aes_id}", response_model=AesRead)
def update_aes(
    aes_id: int,
    payload: AesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> AesIncident:
    """Met à jour le suivi d'une déclaration AES (encadrement)."""
    incident = _get_or_404(db, aes_id)
    if payload.status is not None:
        if payload.status not in AES_STATUSES:
            raise HTTPException(status_code=422, detail=f"Statut invalide : {payload.status}.")
        incident.status = payload.status
        incident.closed_at = utcnow_naive() if payload.status == "closed" else None
    if payload.immediate_measures is not None:
        incident.immediate_measures = payload.immediate_measures
    if payload.source_serology is not None:
        incident.source_serology = payload.source_serology
    if payload.followup_notes is not None:
        incident.followup_notes = payload.followup_notes
    log_audit_event(
        db,
        user=current_user,
        event_type="aes.update",
        entity_type="aes_incident",
        entity_id=str(incident.id),
        payload={"status": incident.status},
    )
    db.commit()
    db.refresh(incident)
    return incident

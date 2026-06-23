"""API — Notifications épidémiologiques (maladies à déclaration obligatoire).

Déclaration et consultation par le personnel clinique ; transmission au district
réservée à l'encadrement (``require_officer``). Cloisonné du comptable au niveau
de l'``api_router``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.epi_notification import EpiNotification
from app.schemas.epi_notification import (
    EPI_STATUSES,
    EpiNotificationCreate,
    EpiNotificationRead,
    EpiNotificationTransmit,
)
from app.services.audit import log_audit_event
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/epi-notifications")


@router.post("", response_model=EpiNotificationRead, status_code=status.HTTP_201_CREATED)
def declare_notification(
    payload: EpiNotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EpiNotification:
    """Déclare une pathologie à notifier (statut initial : à envoyer)."""
    notif = EpiNotification(**payload.model_dump(), declared_by_id=current_user.id, status="to_send")
    db.add(notif)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="epi.declare",
        entity_type="epi_notification",
        entity_id=str(notif.id),
        payload={"pathology": notif.pathology, "quarter": notif.residence_quarter},
    )
    db.commit()
    db.refresh(notif)
    return notif


@router.get("", response_model=list[EpiNotificationRead])
def list_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[EpiNotification]:
    del current_user
    query = db.query(EpiNotification)
    if status_filter:
        query = query.filter(EpiNotification.status == status_filter)
    return query.order_by(EpiNotification.id.desc()).all()


@router.post("/{notif_id}/transmit", response_model=EpiNotificationRead)
def transmit_to_district(
    notif_id: int,
    payload: EpiNotificationTransmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> EpiNotification:
    """Marque la notification comme transmise au district sanitaire (encadrement)."""
    notif = db.query(EpiNotification).filter(EpiNotification.id == notif_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    notif.status = "sent_to_district"
    notif.notified_at = utcnow_naive()
    if payload.channel is not None:
        notif.channel = payload.channel
    log_audit_event(
        db,
        user=current_user,
        event_type="epi.transmit",
        entity_type="epi_notification",
        entity_id=str(notif.id),
        payload={"channel": notif.channel},
    )
    db.commit()
    db.refresh(notif)
    return notif


# Réservé : statuts exposés pour cohérence d'API/documentation.
_ = EPI_STATUSES

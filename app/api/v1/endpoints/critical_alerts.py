"""API — Alertes pour valeurs critiques non-acquittées."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.ruggylab_os import NotifConfig
from app.schemas.notif_config import (
    NotifConfigCreate,
    NotifConfigRead,
    NotifyResult,
    PendingCriticalEntry,
)
from app.services.critical_notifier import check_and_notify, get_pending_criticals
from app.services.expiry_notifier import check_and_notify_expiry, get_expiring_reagents

router = APIRouter(prefix="/critical-alerts")


@router.get("/pending", response_model=list[PendingCriticalEntry])
def list_pending_criticals(
    delay_minutes: int = Query(default=30, ge=1, le=1440),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[dict]:
    """Liste les résultats critiques non-acquittés, avec le délai écoulé."""
    # Use configured delay if available
    cfg = db.query(NotifConfig).filter(NotifConfig.is_active.is_(True)).first()
    effective_delay = cfg.delay_minutes if cfg else delay_minutes
    return get_pending_criticals(db, effective_delay, user=current_user)


@router.post("/check", response_model=NotifyResult)
def trigger_notification_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Déclenche manuellement la vérification et l'envoi des notifications."""
    del current_user
    return check_and_notify(db)


@router.get("/config", response_model=list[NotifConfigRead])
def list_notif_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[NotifConfig]:
    del current_user
    return (
        db.query(NotifConfig).filter(NotifConfig.is_active.is_(True)).order_by(NotifConfig.id).all()
    )


@router.post("/config", response_model=NotifConfigRead, status_code=status.HTTP_201_CREATED)
def create_notif_config(
    payload: NotifConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> NotifConfig:
    del current_user
    cfg = NotifConfig(**payload.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/expiry-alerts")
def list_expiry_alerts(
    days: int = Query(default=30, ge=0, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[dict]:
    """Réactifs expirant dans les ``days`` prochains jours."""
    del current_user
    return get_expiring_reagents(db, days=days)


@router.post("/expiry-check")
def trigger_expiry_notification(
    days: int = Query(default=30, ge=0, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Envoie des webhooks pour les réactifs expirant bientôt."""
    del current_user
    return check_and_notify_expiry(db, days=days)


@router.delete("/config/{config_id}", status_code=status.HTTP_200_OK)
def deactivate_notif_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    cfg = db.query(NotifConfig).filter(NotifConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration de notification introuvable.",
        )
    cfg.is_active = False
    db.commit()
    return {"status": "deactivated"}

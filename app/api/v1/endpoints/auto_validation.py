"""Auto-validation ISO 15189 §5.8 — configuration et déclenchement."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.ruggylab_os import AutoValidationConfig
from app.schemas.auto_validation import (
    AutoValidationConfigCreate,
    AutoValidationConfigRead,
    AutoValidationRunResult,
)
from app.services.auto_validator import batch_auto_validate

router = APIRouter(prefix="/auto-validation")


@router.get("/config", response_model=list[AutoValidationConfigRead])
def list_auto_validation_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[AutoValidationConfig]:
    """Liste les règles d'auto-validation actives."""
    del current_user
    return (
        db.query(AutoValidationConfig)
        .filter(AutoValidationConfig.is_active.is_(True))
        .order_by(AutoValidationConfig.id)
        .all()
    )


@router.post(
    "/config",
    response_model=AutoValidationConfigRead,
    status_code=status.HTTP_201_CREATED,
)
def create_auto_validation_config(
    payload: AutoValidationConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> AutoValidationConfig:
    """Crée une nouvelle règle d'auto-validation."""
    del current_user
    cfg = AutoValidationConfig(**payload.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@router.delete("/config/{config_id}", status_code=status.HTTP_200_OK)
def deactivate_auto_validation_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    """Désactive une règle d'auto-validation (suppression logique)."""
    del current_user
    cfg = db.query(AutoValidationConfig).filter(AutoValidationConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Règle d'auto-validation introuvable.",
        )
    cfg.is_active = False
    db.commit()
    return {"status": "deactivated"}


@router.post("/run", response_model=AutoValidationRunResult)
def run_auto_validation(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict:
    """Applique l'auto-validation sur les résultats validés non encore traités (max 200).

    Utile pour traiter rétroactivement les résultats existants après configuration
    d'une nouvelle règle.
    """
    del current_user
    return batch_auto_validate(db)

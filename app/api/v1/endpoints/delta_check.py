"""API — Règles de delta-check patient."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.ruggylab_os import DeltaCheckRule
from app.schemas.delta_check import DeltaCheckRuleCreate, DeltaCheckRuleRead

router = APIRouter(prefix="/delta-check-rules")


@router.get("", response_model=list[DeltaCheckRuleRead])
def list_delta_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[DeltaCheckRule]:
    del current_user
    return (
        db.query(DeltaCheckRule)
        .filter(DeltaCheckRule.is_active.is_(True))
        .order_by(DeltaCheckRule.analyte)
        .all()
    )


@router.post("", response_model=DeltaCheckRuleRead, status_code=status.HTTP_201_CREATED)
def create_delta_rule(
    payload: DeltaCheckRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> DeltaCheckRule:
    del current_user
    existing = (
        db.query(DeltaCheckRule)
        .filter(
            DeltaCheckRule.analyte.ilike(payload.analyte),
            DeltaCheckRule.is_active.is_(True),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Une règle delta-check active existe déjà pour l'analyte '{payload.analyte}'.",
        )
    rule = DeltaCheckRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
def deactivate_delta_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    rule = db.query(DeltaCheckRule).filter(DeltaCheckRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Règle delta-check introuvable.",
        )
    rule.is_active = False
    db.commit()
    return {"status": "deactivated"}

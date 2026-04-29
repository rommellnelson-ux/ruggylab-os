from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_admin
from app.db.session import get_db
from app.models import Equipment, EquipmentReagentRatio, Reagent, User
from app.schemas.equipment_reagent_ratio import (
    EquipmentReagentRatioCreate,
    EquipmentReagentRatioRead,
    EquipmentReagentRatioUpdate,
    EquipmentReagentRatioVersionRead,
)
from app.schemas.pagination import EquipmentReagentRatioListResponse, PaginationMeta
from app.services.audit import log_audit_event
from app.services.ratio_management import create_ratio_version

router = APIRouter(prefix="/equipment-reagent-ratios")


@router.get(
    "",
    response_model=EquipmentReagentRatioListResponse,
    dependencies=[Depends(require_admin)],
)
def list_ratios(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    equipment_id: int | None = Query(default=None, ge=1),
    reagent_id: int | None = Query(default=None, ge=1),
) -> EquipmentReagentRatioListResponse:
    query = db.query(EquipmentReagentRatio)
    if equipment_id is not None:
        query = query.filter(EquipmentReagentRatio.equipment_id == equipment_id)
    if reagent_id is not None:
        query = query.filter(EquipmentReagentRatio.reagent_id == reagent_id)
    total = query.with_entities(func.count(EquipmentReagentRatio.id)).scalar() or 0
    items = (
        query.order_by(EquipmentReagentRatio.id.desc()).offset(skip).limit(limit).all()
    )
    return EquipmentReagentRatioListResponse(
        items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit)
    )


@router.get(
    "/{ratio_id}/versions",
    response_model=list[EquipmentReagentRatioVersionRead],
    dependencies=[Depends(require_admin)],
)
def list_ratio_versions(
    ratio_id: int, db: Session = Depends(get_db)
) -> list[EquipmentReagentRatioVersionRead]:
    ratio = (
        db.query(EquipmentReagentRatio)
        .filter(EquipmentReagentRatio.id == ratio_id)
        .first()
    )
    if not ratio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ratio introuvable."
        )
    return [
        EquipmentReagentRatioVersionRead(
            id=version.id,
            ratio_id=version.ratio_id,
            version_number=version.version_number,
            equipment_id=version.equipment_id,
            reagent_id=version.reagent_id,
            consumption_per_run=version.consumption_per_run,
            adjustment_factor=version.adjustment_factor,
            notes=version.notes,
            is_active=version.is_active,
            changed_by_user_id=version.changed_by_user_id,
            change_reason=version.change_reason,
            created_at=version.created_at.isoformat(),
        )
        for version in ratio.versions
    ]


@router.post(
    "",
    response_model=EquipmentReagentRatioRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_ratio(
    payload: EquipmentReagentRatioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EquipmentReagentRatio:
    equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    reagent = db.query(Reagent).filter(Reagent.id == payload.reagent_id).first()
    if not equipment or not reagent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipement ou reactif introuvable.",
        )
    existing = (
        db.query(EquipmentReagentRatio)
        .filter(
            EquipmentReagentRatio.equipment_id == payload.equipment_id,
            EquipmentReagentRatio.reagent_id == payload.reagent_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ratio deja existant pour ce couple.",
        )
    ratio = EquipmentReagentRatio(**payload.model_dump())
    db.add(ratio)
    db.flush()
    create_ratio_version(
        db, ratio=ratio, changed_by_user=current_user, change_reason="Initial creation"
    )
    log_audit_event(
        db,
        user=current_user,
        event_type="equipment_reagent_ratio.create",
        entity_type="equipment_reagent_ratio",
        entity_id=str(ratio.id),
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(ratio)
    return ratio


@router.put(
    "/{ratio_id}",
    response_model=EquipmentReagentRatioRead,
    dependencies=[Depends(require_admin)],
)
def update_ratio(
    ratio_id: int,
    payload: EquipmentReagentRatioUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EquipmentReagentRatio:
    ratio = (
        db.query(EquipmentReagentRatio)
        .filter(EquipmentReagentRatio.id == ratio_id)
        .first()
    )
    if not ratio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ratio introuvable."
        )
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(ratio, key, value)
    create_ratio_version(
        db, ratio=ratio, changed_by_user=current_user, change_reason="Admin update"
    )
    log_audit_event(
        db,
        user=current_user,
        event_type="equipment_reagent_ratio.update",
        entity_type="equipment_reagent_ratio",
        entity_id=str(ratio.id),
        payload=payload.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(ratio)
    return ratio


@router.delete(
    "/{ratio_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_admin)]
)
def delete_ratio(
    ratio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    ratio = (
        db.query(EquipmentReagentRatio)
        .filter(EquipmentReagentRatio.id == ratio_id)
        .first()
    )
    if not ratio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ratio introuvable."
        )
    log_audit_event(
        db,
        user=current_user,
        event_type="equipment_reagent_ratio.delete",
        entity_type="equipment_reagent_ratio",
        entity_id=str(ratio.id),
        payload={"equipment_id": ratio.equipment_id, "reagent_id": ratio.reagent_id},
    )
    db.delete(ratio)
    db.commit()
    return {"status": "deleted"}

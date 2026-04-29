from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_admin
from app.db.session import get_db
from app.models import (
    Equipment,
    EquipmentReagentRatio,
    RatioPreset,
    RatioPresetItem,
    Reagent,
    User,
)
from app.schemas.pagination import (
    PaginationMeta,
    RatioPresetItemListResponse,
    RatioPresetListResponse,
)
from app.schemas.ratio_preset import (
    RatioPresetCreate,
    RatioPresetItemCreate,
    RatioPresetItemRead,
    RatioPresetRead,
)
from app.services.audit import log_audit_event
from app.services.ratio_management import create_ratio_version

router = APIRouter(prefix="/ratio-presets")


@router.get(
    "", response_model=RatioPresetListResponse, dependencies=[Depends(require_admin)]
)
def list_presets(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> RatioPresetListResponse:
    query = db.query(RatioPreset)
    total = query.with_entities(func.count(RatioPreset.id)).scalar() or 0
    items = query.order_by(RatioPreset.id.desc()).offset(skip).limit(limit).all()
    return RatioPresetListResponse(
        items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit)
    )


@router.post(
    "",
    response_model=RatioPresetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_preset(
    payload: RatioPresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RatioPreset:
    existing = db.query(RatioPreset).filter(RatioPreset.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Preset deja existant."
        )
    preset = RatioPreset(**payload.model_dump())
    db.add(preset)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="ratio_preset.create",
        entity_type="ratio_preset",
        entity_id=str(preset.id),
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(preset)
    return preset


@router.get(
    "/{preset_id}/items",
    response_model=RatioPresetItemListResponse,
    dependencies=[Depends(require_admin)],
)
def list_preset_items(
    preset_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> RatioPresetItemListResponse:
    query = db.query(RatioPresetItem).filter(RatioPresetItem.preset_id == preset_id)
    total = query.with_entities(func.count(RatioPresetItem.id)).scalar() or 0
    items = query.order_by(RatioPresetItem.id.asc()).offset(skip).limit(limit).all()
    return RatioPresetItemListResponse(
        items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit)
    )


@router.post(
    "/items",
    response_model=RatioPresetItemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_preset_item(
    payload: RatioPresetItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RatioPresetItem:
    preset = db.query(RatioPreset).filter(RatioPreset.id == payload.preset_id).first()
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preset introuvable."
        )
    item = RatioPresetItem(**payload.model_dump())
    db.add(item)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="ratio_preset_item.create",
        entity_type="ratio_preset_item",
        entity_id=str(item.id),
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/{preset_id}/apply",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
def apply_preset(
    preset_id: int,
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, int]:
    preset = db.query(RatioPreset).filter(RatioPreset.id == preset_id).first()
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not preset or not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset ou equipement introuvable.",
        )
    if not preset.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preset inactif: application impossible.",
        )

    applied = 0
    for item in preset.items:
        if not item.is_active:
            continue
        reagent = db.query(Reagent).filter(Reagent.name == item.reagent_name).first()
        if not reagent:
            reagent = Reagent(
                name=item.reagent_name,
                category=item.reagent_category,
                unit=item.reagent_unit,
                current_stock=0.0,
                alert_threshold=0.0,
            )
            db.add(reagent)
            db.flush()

        ratio = (
            db.query(EquipmentReagentRatio)
            .filter(
                EquipmentReagentRatio.equipment_id == equipment_id,
                EquipmentReagentRatio.reagent_id == reagent.id,
            )
            .first()
        )

        if ratio:
            ratio.consumption_per_run = item.consumption_per_run
            ratio.adjustment_factor = item.adjustment_factor
            ratio.notes = item.notes
            ratio.is_active = item.is_active
            create_ratio_version(
                db,
                ratio=ratio,
                changed_by_user=current_user,
                change_reason=f"Applied preset {preset.name}",
            )
        else:
            ratio = EquipmentReagentRatio(
                equipment_id=equipment_id,
                reagent_id=reagent.id,
                consumption_per_run=item.consumption_per_run,
                adjustment_factor=item.adjustment_factor,
                notes=item.notes,
                is_active=item.is_active,
            )
            db.add(ratio)
            db.flush()
            create_ratio_version(
                db,
                ratio=ratio,
                changed_by_user=current_user,
                change_reason=f"Applied preset {preset.name}",
            )
        applied += 1

    log_audit_event(
        db,
        user=current_user,
        event_type="ratio_preset.apply",
        entity_type="ratio_preset",
        entity_id=str(preset.id),
        payload={"equipment_id": equipment_id, "applied_count": applied},
    )
    db.commit()
    return {"applied_count": applied}

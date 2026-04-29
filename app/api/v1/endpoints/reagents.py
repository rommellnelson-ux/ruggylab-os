from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import EquipmentReagentRatio, Reagent, StockMovement, User
from app.schemas.pagination import PaginationMeta, ReagentListResponse
from app.schemas.reagent import ReagentCreate, ReagentRead
from app.services.audit import log_audit_event

router = APIRouter(prefix="/reagents")


@router.get("", response_model=ReagentListResponse)
def list_reagents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1),
) -> ReagentListResponse:
    del current_user
    query = db.query(Reagent)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(Reagent.name.ilike(search))
    total = query.with_entities(func.count(Reagent.id)).scalar() or 0
    items = query.order_by(Reagent.id.desc()).offset(skip).limit(limit).all()
    return ReagentListResponse(
        items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit)
    )


@router.get("/{reagent_id}", response_model=ReagentRead)
def get_reagent(
    reagent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Reagent:
    del current_user
    reagent = db.query(Reagent).filter(Reagent.id == reagent_id).first()
    if not reagent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reactif introuvable."
        )
    return reagent


@router.post("", response_model=ReagentRead, status_code=status.HTTP_201_CREATED)
def create_reagent(
    payload: ReagentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Reagent:
    existing = db.query(Reagent).filter(Reagent.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reactif deja existant: {payload.name}.",
        )

    reagent = Reagent(**payload.model_dump())
    db.add(reagent)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="reagent.create",
        entity_type="reagent",
        entity_id=str(reagent.id),
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(reagent)
    return reagent


@router.put("/{reagent_id}", response_model=ReagentRead)
def update_reagent(
    reagent_id: int,
    payload: ReagentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Reagent:
    reagent = db.query(Reagent).filter(Reagent.id == reagent_id).first()
    if not reagent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reactif introuvable."
        )

    existing = (
        db.query(Reagent)
        .filter(Reagent.name == payload.name, Reagent.id != reagent_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reactif deja existant: {payload.name}.",
        )

    for key, value in payload.model_dump().items():
        setattr(reagent, key, value)

    log_audit_event(
        db,
        user=current_user,
        event_type="reagent.update",
        entity_type="reagent",
        entity_id=str(reagent.id),
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(reagent)
    return reagent


@router.delete("/{reagent_id}", status_code=status.HTTP_200_OK)
def delete_reagent(
    reagent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    reagent = db.query(Reagent).filter(Reagent.id == reagent_id).first()
    if not reagent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reactif introuvable."
        )

    linked_ratios = (
        db.query(EquipmentReagentRatio)
        .filter(EquipmentReagentRatio.reagent_id == reagent_id)
        .count()
    )
    if linked_ratios > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Suppression impossible: ce reactif est encore utilise dans des ratios de consommation.",
        )
    linked_movements = (
        db.query(StockMovement).filter(StockMovement.reagent_id == reagent_id).count()
    )
    if linked_movements > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Suppression impossible: ce reactif possede un historique de mouvements de stock.",
        )

    log_audit_event(
        db,
        user=current_user,
        event_type="reagent.delete",
        entity_type="reagent",
        entity_id=str(reagent.id),
        payload={"name": reagent.name},
    )
    db.delete(reagent)
    db.commit()
    return {"status": "deleted"}

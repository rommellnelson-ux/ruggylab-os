"""API — Lots de réactifs : traçabilité fine et consommation FEFO.

FEFO = First-Expired-First-Out : on consomme en priorité le lot dont la
péremption est la plus proche.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Reagent, User
from app.models.reagent_lot import ReagentLot
from app.schemas.reagent_lot import ReagentLotConsume, ReagentLotCreate, ReagentLotRead

router = APIRouter(prefix="/reagent-lots")


def _fefo_order(query: SAQuery[ReagentLot]) -> SAQuery[ReagentLot]:
    """Tri FEFO : péremption la plus proche d'abord, lots sans date en dernier."""
    return query.order_by(
        case((ReagentLot.expiry_date.is_(None), 1), else_=0),
        ReagentLot.expiry_date.asc(),
        ReagentLot.id.asc(),
    )


@router.post("", response_model=ReagentLotRead, status_code=status.HTTP_201_CREATED)
def add_lot(
    payload: ReagentLotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReagentLot:
    """Réceptionne un lot de réactif."""
    del current_user
    if not db.query(Reagent).filter(Reagent.id == payload.reagent_id).first():
        raise HTTPException(status_code=404, detail="Réactif introuvable.")
    lot = ReagentLot(**payload.model_dump(), status="active")
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@router.get("", response_model=list[ReagentLotRead])
def list_lots(
    reagent_id: int | None = Query(default=None),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ReagentLot]:
    """Liste les lots (ordre FEFO)."""
    del current_user
    query = db.query(ReagentLot)
    if reagent_id is not None:
        query = query.filter(ReagentLot.reagent_id == reagent_id)
    if active_only:
        query = query.filter(ReagentLot.status == "active", ReagentLot.quantity > 0)
    lots: list[ReagentLot] = _fefo_order(query).all()
    return lots


@router.post("/consume", response_model=list[ReagentLotRead])
def consume_fefo(
    payload: ReagentLotConsume,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ReagentLot]:
    """Consomme une quantité sur les lots du réactif en FEFO (péremption la plus proche)."""
    del current_user
    lots: list[ReagentLot] = _fefo_order(
        db.query(ReagentLot).filter(
            ReagentLot.reagent_id == payload.reagent_id,
            ReagentLot.status == "active",
            ReagentLot.quantity > 0,
        )
    ).all()
    available = sum(lot.quantity for lot in lots)
    if payload.quantity > available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Quantité insuffisante (demandé {payload.quantity}, disponible {available}).",
        )
    remaining = payload.quantity
    touched: list[ReagentLot] = []
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.quantity, remaining)
        lot.quantity -= take
        remaining -= take
        if lot.quantity <= 0:
            lot.status = "exhausted"
        touched.append(lot)
    db.commit()
    for lot in touched:
        db.refresh(lot)
    return touched

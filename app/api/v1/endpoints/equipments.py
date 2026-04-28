from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, User
from app.schemas.equipment import EquipmentCreate, EquipmentRead


router = APIRouter(prefix="/equipments")


@router.get("", response_model=list[EquipmentRead])
def list_equipments(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> list[Equipment]:
    del current_user
    return db.query(Equipment).order_by(Equipment.id.desc()).all()


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Equipment:
    del current_user
    if payload.serial_number:
        existing = db.query(Equipment).filter(Equipment.serial_number == payload.serial_number).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Equipement déjà existant pour le numéro de série {payload.serial_number}.",
            )

    equipment = Equipment(**payload.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, User
from app.models.ruggylab_os import EquipmentMaintenance
from app.schemas.equipment_maintenance import EquipmentMaintenanceCreate, EquipmentMaintenanceRead
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/equipment-maintenance")


@router.get("", response_model=list[EquipmentMaintenanceRead])
def list_maintenances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    equipment_id: int | None = Query(default=None, ge=1),
    is_completed: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EquipmentMaintenance]:
    del current_user
    q = db.query(EquipmentMaintenance)
    if equipment_id is not None:
        q = q.filter(EquipmentMaintenance.equipment_id == equipment_id)
    if is_completed is not None:
        q = q.filter(EquipmentMaintenance.is_completed == is_completed)
    return q.order_by(EquipmentMaintenance.id.desc()).limit(limit).all()


@router.get("/due", response_model=list[EquipmentMaintenanceRead])
def list_due_maintenances(
    days: int = Query(default=7, ge=0, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[EquipmentMaintenance]:
    """Maintenances non-terminées dont l'échéance est dans les N prochains jours."""
    del current_user
    cutoff = utcnow_naive() + dt.timedelta(days=days)
    return (
        db.query(EquipmentMaintenance)
        .filter(
            EquipmentMaintenance.is_completed.is_(False),
            EquipmentMaintenance.next_due_at.isnot(None),
            EquipmentMaintenance.next_due_at <= cutoff,
        )
        .order_by(EquipmentMaintenance.next_due_at.asc())
        .all()
    )


@router.post("", response_model=EquipmentMaintenanceRead, status_code=status.HTTP_201_CREATED)
def create_maintenance(
    payload: EquipmentMaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EquipmentMaintenance:
    del current_user
    equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Équipement introuvable pour l'identifiant {payload.equipment_id}.",
        )
    m = EquipmentMaintenance(**payload.model_dump(exclude_none=True))
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.patch("/{maintenance_id}/complete", response_model=EquipmentMaintenanceRead)
def complete_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EquipmentMaintenance:
    """Marque une maintenance comme effectuée et horodate l'exécution."""
    m = db.query(EquipmentMaintenance).filter(EquipmentMaintenance.id == maintenance_id).first()
    if not m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance introuvable."
        )
    if m.is_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Maintenance déjà terminée."
        )
    m.is_completed = True
    m.performed_at = utcnow_naive()
    m.performed_by_id = current_user.id
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{maintenance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    del current_user
    m = db.query(EquipmentMaintenance).filter(EquipmentMaintenance.id == maintenance_id).first()
    if not m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance introuvable."
        )
    db.delete(m)
    db.commit()

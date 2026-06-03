from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import CriticalRange, User
from app.schemas.critical_range import CriticalRangeCreate, CriticalRangeRead

router = APIRouter(prefix="/critical-ranges")


@router.get("", response_model=list[CriticalRangeRead])
def list_critical_ranges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[CriticalRange]:
    del current_user
    return (
        db.query(CriticalRange)
        .filter(CriticalRange.is_active.is_(True))
        .order_by(CriticalRange.analyte)
        .all()
    )


@router.post("", response_model=CriticalRangeRead, status_code=status.HTTP_201_CREATED)
def create_critical_range(
    payload: CriticalRangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> CriticalRange:
    del current_user
    existing = (
        db.query(CriticalRange)
        .filter(
            CriticalRange.analyte.ilike(payload.analyte),
            CriticalRange.is_active.is_(True),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un seuil critique actif existe déjà pour l'analyte '{payload.analyte}'.",
        )
    cr = CriticalRange(**payload.model_dump())
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


@router.delete("/{range_id}", status_code=status.HTTP_200_OK)
def deactivate_critical_range(
    range_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    cr = db.query(CriticalRange).filter(CriticalRange.id == range_id).first()
    if not cr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seuil critique introuvable."
        )
    cr.is_active = False
    db.commit()
    return {"status": "deactivated"}

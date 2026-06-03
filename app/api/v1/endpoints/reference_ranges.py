"""API — Valeurs de référence par analyte/sexe/âge."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.models.ruggylab_os import ReferenceRange
from app.schemas.reference_range import ReferenceRangeCreate, ReferenceRangeRead

router = APIRouter(prefix="/reference-ranges")


@router.get("", response_model=list[ReferenceRangeRead])
def list_reference_ranges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ReferenceRange]:
    del current_user
    return (
        db.query(ReferenceRange)
        .filter(ReferenceRange.is_active.is_(True))
        .order_by(ReferenceRange.analyte, ReferenceRange.sex)
        .all()
    )


@router.post("", response_model=ReferenceRangeRead, status_code=status.HTTP_201_CREATED)
def create_reference_range(
    payload: ReferenceRangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> ReferenceRange:
    del current_user
    rr = ReferenceRange(**payload.model_dump())
    db.add(rr)
    db.commit()
    db.refresh(rr)
    return rr


@router.delete("/{range_id}", status_code=status.HTTP_200_OK)
def deactivate_reference_range(
    range_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    rr = db.query(ReferenceRange).filter(ReferenceRange.id == range_id).first()
    if not rr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plage de référence introuvable.",
        )
    rr.is_active = False
    db.commit()
    return {"status": "deactivated"}

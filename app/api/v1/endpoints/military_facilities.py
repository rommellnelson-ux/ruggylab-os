from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import MilitaryFacility, User
from app.schemas.military_facility import MilitaryFacilityRead

router = APIRouter(prefix="/military-facilities")


@router.get("", response_model=list[MilitaryFacilityRead])
def list_military_facilities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[MilitaryFacility]:
    del current_user
    return db.query(MilitaryFacility).order_by(MilitaryFacility.name).all()

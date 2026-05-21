from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import MilitaryFacility
from app.schemas.military_facility import MilitaryFacilityRead

router = APIRouter(prefix="/military-facilities")


@router.get("", response_model=list[MilitaryFacilityRead])
def list_military_facilities(
    db: Session = Depends(get_db),
) -> list[MilitaryFacility]:
    return db.query(MilitaryFacility).order_by(MilitaryFacility.name).all()

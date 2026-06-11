"""API — Référentiel biologique : valeurs de référence + interprétation."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import BiologicalReferenceRange, User
from app.schemas.bioref import BioRefInterpretRequest, BioRefRangeRead
from app.services.bioref_service import interpret, seed_bioref

router = APIRouter(prefix="/bioref")


@router.get("/ranges", response_model=list[BioRefRangeRead])
def list_ranges(
    test_code: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[BiologicalReferenceRange]:
    """Liste les valeurs de référence actives (filtres optionnels)."""
    del current_user
    query = db.query(BiologicalReferenceRange).filter(
        BiologicalReferenceRange.is_active.is_(True)
    )
    if test_code:
        query = query.filter(BiologicalReferenceRange.test_code == test_code)
    if category:
        query = query.filter(BiologicalReferenceRange.category == category)
    return query.order_by(
        BiologicalReferenceRange.category, BiologicalReferenceRange.test_code
    ).all()


@router.post("/seed-defaults")
def seed_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, int]:
    """Charge le référentiel biologique standard (IFCC/Tietz/OMS…). Idempotent."""
    del current_user
    return {"created": seed_bioref(db)}


@router.post("/interpret")
def interpret_result(
    payload: BioRefInterpretRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Interprète une valeur : flag (NORMAL/BAS/HAUT/CRITIQUE) + plage + note clinique."""
    del current_user
    return interpret(db, payload.test_code, payload.value, payload.sex, payload.age_years)

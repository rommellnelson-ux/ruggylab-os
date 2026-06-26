"""File de travail consolidée pour agents et responsables laboratoire."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import User
from app.schemas.worklist import WorklistResponse
from app.services.worklist import build_my_worklist

router = APIRouter(prefix="/worklist")


@router.get("/my", response_model=WorklistResponse)
def my_worklist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(default=60, ge=1, le=200),
    category: str | None = Query(default=None),
) -> WorklistResponse:
    """Retourne les actions terrain prioritaires dans une file unique."""
    return build_my_worklist(db, current_user, limit=limit, category=category)

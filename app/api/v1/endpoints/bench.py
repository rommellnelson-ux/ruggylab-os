"""API Vue Paillasse — files d'action pré-filtrées côté serveur."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import User
from app.schemas.bench import BenchRadarResponse
from app.services.bench_radar import build_bench_radar

router = APIRouter(prefix="/bench")


@router.get("/radar", response_model=BenchRadarResponse)
def bench_radar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Retourne uniquement les files utiles à la paillasse.

    Les filtres métier (critique non traité, TAT < 15 min, routine à valider)
    sont appliqués ici pour éviter de pousser tout le cockpit au navigateur.
    """
    return build_bench_radar(db, current_user)

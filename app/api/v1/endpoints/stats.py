"""Endpoint de statistiques de performance du laboratoire."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import User
from app.services.lab_stats import compute_stats_summary

router = APIRouter(prefix="/stats")


@router.get(
    "/summary",
    summary="Statistiques de performance laboratoire (TAT, taux critique, QC, maintenance)",
)
def stats_summary(
    days: int = Query(default=30, ge=1, le=365, description="Fenêtre d'analyse en jours"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Retourne un résumé des indicateurs clés de performance sur la période demandée :

    - Volume total de résultats et taux de valeurs critiques
    - TAT (turnaround time) moyen/min/max/p95 par équipement
    - Volumes hebdomadaires sur les 8 dernières semaines
    - Taux de violations QC analytique
    - Nombre de maintenances équipements échues dans les 7 prochains jours
    """
    del current_user
    return compute_stats_summary(db, days=days)

"""Endpoint du tableau de bord épidémiologique.

POST /api/v1/epidemiology/dashboard
  Authentification Bearer requise.
  Corps : EpidemiologyRequest (JSON)
  Réponse : EpidemiologyDashboard (JSON)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import User
from app.schemas.epidemiology import EpidemiologyDashboard, EpidemiologyRequest
from app.services.epidemiology_service import compute_dashboard

router = APIRouter(prefix="/epidemiology")


@router.post(
    "/dashboard",
    response_model=EpidemiologyDashboard,
    summary="Tableau de bord épidémiologique",
    description=(
        "Calcule les statistiques épidémiologiques (taux de critiques, tendances journalières, "
        "répartition par paramètre et par établissement) pour la période demandée."
    ),
)
def epidemiology_dashboard(
    payload: EpidemiologyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> EpidemiologyDashboard:
    """Retourne le tableau de bord épidémiologique.

    - Filtre par date (défaut : 30 derniers jours)
    - Filtre optionnel par identifiant d'équipement (``facility_ids``)
    - Filtre optionnel par paramètre biologique (``parameters``)
    """
    del current_user  # Authentification vérifiée par la dépendance
    return compute_dashboard(db, payload)

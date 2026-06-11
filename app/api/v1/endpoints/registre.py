"""API — Registre maître : prévisualisation, analyse rétrospective, import.

Les lignes du registre sont postées en JSON (le client extrait le tableur).
Aucune donnée patient n'est conservée hors d'un import explicitement confirmé.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import User
from app.schemas.registre import RegistreImportRequest, RegistreRowsRequest
from app.services.registre_analytics import compute_registre_analytics
from app.services.registre_import import RegistreImportTooLargeError, import_registre_rows
from app.services.registre_parser import build_import_preview

router = APIRouter(prefix="/registre")


@router.post("/preview")
def registre_preview(
    payload: RegistreRowsRequest,
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Prévisualisation (dry-run) : reconnaissance des examens, montants, alertes.

    N'écrit rien en base.
    """
    del current_user
    return build_import_preview(payload.rows)


@router.post("/analytics")
def registre_analytics(
    payload: RegistreRowsRequest,
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Analyse rétrospective : volumes, recettes/CMU, top examens, paludisme, mensuel."""
    del current_user
    return compute_registre_analytics(payload.rows)


@router.post("/import")
def registre_import(
    payload: RegistreImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict:
    """Importe le registre en Patients/Échantillons/Résultats (réservé officier/admin).

    Un import réel exige ``dry_run=false`` ET ``confirm=true`` (double garde-fou).
    Chaque ligne est isolée dans un savepoint ; l'opération est auditée.
    """
    if not payload.dry_run and not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import réel : 'confirm' doit être true (dry_run=false).",
        )
    try:
        return import_registre_rows(
            db, payload.rows, user=current_user, dry_run=payload.dry_run
        )
    except RegistreImportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

"""Import en lot CSV — patients et réactifs. Réservé aux officiers/admins."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_officer
from app.db.session import get_db
from app.models import User
from app.schemas.bulk_import import BulkImportRequest, BulkImportResult
from app.services.bulk_import import BulkImportTooLarge, import_patients, import_reagents

router = APIRouter(prefix="/bulk-import")


@router.post("/patients", response_model=BulkImportResult)
def bulk_import_patients(
    payload: BulkImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict:
    """Importe des patients depuis un CSV.

    Colonnes : ipp_unique_id, first_name, last_name, birth_date, sex, rank.
    """
    del current_user
    try:
        return import_patients(db, payload.csv, dry_run=payload.dry_run)
    except BulkImportTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))


@router.post("/reagents", response_model=BulkImportResult)
def bulk_import_reagents(
    payload: BulkImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict:
    """Importe des réactifs depuis un CSV.

    Colonnes : name, category, unit, current_stock, alert_threshold,
    lot_number, expiry_date, supplier.
    """
    del current_user
    try:
        return import_reagents(db, payload.csv, dry_run=payload.dry_run)
    except BulkImportTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))

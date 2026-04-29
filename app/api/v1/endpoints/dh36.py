from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import User
from app.schemas.dh36_ingestion import DH36IngestRequest, DH36IngestResponse
from app.services.interfacing.dh36_ingestion import ingest_dh36_message

router = APIRouter(prefix="/dh36")


@router.post(
    "/ingest",
    response_model=DH36IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_message(
    payload: DH36IngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DH36IngestResponse:
    try:
        outcome = ingest_dh36_message(
            db,
            raw_message=payload.raw_message,
            user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    message = outcome.message
    response_status = "duplicate" if outcome.duplicate else message.status
    return DH36IngestResponse(
        message_id=message.id,
        status=response_status,
        result_id=message.result_id,
        sample_barcode=message.sample_barcode,
        message_control_id=message.message_control_id,
        rejection_reason=message.rejection_reason,
        processed_at=message.processed_at,
    )

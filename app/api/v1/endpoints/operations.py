from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_officer
from app.db.session import get_db
from app.models import Reagent, User
from app.schemas.operations import ValidateOrderRequest
from app.services.audit import log_audit_event


router = APIRouter(prefix="/operations")


@router.post("/validate-order")
def validate_reagent_order(
    payload: ValidateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str | int | None]:
    reagent_name = None
    if payload.reagent_id is not None:
        reagent = db.query(Reagent).filter(Reagent.id == payload.reagent_id).first()
        if reagent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reactif introuvable.")
        reagent_name = reagent.name

    log_audit_event(
        db,
        user=current_user,
        event_type="operation.validate_order",
        entity_type="reagent_order",
        entity_id=payload.order_reference or (str(payload.reagent_id) if payload.reagent_id is not None else None),
        payload={
            "reagent_id": payload.reagent_id,
            "reagent_name": reagent_name,
            "order_reference": payload.order_reference,
            "notes": payload.notes,
        },
    )
    db.commit()
    return {
        "status": "Commande validee et signee electroniquement.",
        "validated_by": current_user.username,
        "reagent_id": payload.reagent_id,
    }

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.db.session import get_db
from app.models import Equipment, Result, Sample
from app.services.audit import log_audit_event
from app.services.imaging.capture_service import MicroscopeCaptureService

router = APIRouter(prefix="/imaging")
microscope_service = MicroscopeCaptureService(
    storage_dir=settings.MICROSCOPY_STORAGE_DIR
)


@router.post("/capture-microscope", status_code=status.HTTP_201_CREATED)
def trigger_microscope_capture(
    sample_barcode: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict[str, Any]:
    sample = db.query(Sample).filter(Sample.barcode == sample_barcode).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Code-barres inconnu dans RuggyLab OS: {sample_barcode}.",
        )

    equipment = db.query(Equipment).filter(Equipment.name == "Magnus Theia-i").first()
    image_path = microscope_service.reserve_image_path(sample_barcode)

    new_result = Result(
        sample_id=sample.id,
        equipment_id=equipment.id if equipment else None,
        data_points={},
        image_url=image_path,
        validator_id=current_user.id,
        is_validated=False,
        is_critical=False,
    )
    db.add(new_result)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="imaging.capture.reserve",
        entity_type="result",
        entity_id=str(new_result.id),
        payload={"sample_barcode": sample_barcode, "image_url": image_path},
    )
    db.commit()
    db.refresh(new_result)

    return {
        "status": "success",
        "message": "Reservation d'emplacement image effectuee.",
        "image_url": image_path,
        "result_id": new_result.id,
    }

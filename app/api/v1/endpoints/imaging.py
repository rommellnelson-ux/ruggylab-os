from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.db.session import get_db
from app.models import Equipment, MalariaAnalysisJob, Result, Sample, User
from app.schemas.malaria import MalariaAnalysisRead
from app.services.audit import log_audit_event
from app.services.imaging.capture_service import MicroscopeCaptureService
from app.services.malaria_ai import (
    enqueue_malaria_analysis,
    process_malaria_job,
    process_malaria_job_background,
)
from app.services.patient_access import can_access_patient, can_access_result

router = APIRouter(prefix="/imaging")
microscope_service = MicroscopeCaptureService(storage_dir=settings.MICROSCOPY_STORAGE_DIR)

_OUT_OF_SCOPE = "Accès refusé : dossier hors de votre périmètre."


def _require_result_access(current_user: User, result: Result) -> None:
    """403 si le résultat (via son patient) est hors du périmètre de l'agent."""
    if not can_access_result(current_user, result):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUT_OF_SCOPE)


@router.post("/capture-microscope", status_code=status.HTTP_201_CREATED)
def trigger_microscope_capture(
    sample_barcode: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    sample = db.query(Sample).filter(Sample.barcode == sample_barcode).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Code-barres inconnu dans RuggyLab OS: {sample_barcode}.",
        )
    if sample.patient is not None and not can_access_patient(current_user, sample.patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_OUT_OF_SCOPE)

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


@router.post(
    "/malaria/analyze/{result_id}",
    response_model=MalariaAnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_malaria_analysis(
    result_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MalariaAnalysisJob:
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resultat introuvable.",
        )
    _require_result_access(current_user, result)
    if not result.image_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analyse paludisme impossible: aucune image microscope liee au resultat.",
        )

    # Check for completed job first (no lock needed)
    completed_job = (
        db.query(MalariaAnalysisJob)
        .filter(
            MalariaAnalysisJob.result_id == result_id,
            MalariaAnalysisJob.status == "completed",
        )
        .first()
    )
    if completed_job:
        return completed_job

    # Check for active job with lock to prevent race conditions
    active_job = (
        db.query(MalariaAnalysisJob)
        .filter(
            MalariaAnalysisJob.result_id == result_id,
            MalariaAnalysisJob.status.in_(["queued", "processing"]),
        )
        .with_for_update()
        .first()
    )
    if active_job:
        return active_job

    job = enqueue_malaria_analysis(db, result=result, user=current_user)
    if settings.MALARIA_ANALYSIS_AUTORUN and not settings.TESTING:
        background_tasks.add_task(process_malaria_job_background, job.id)
    return job


@router.post(
    "/malaria/jobs/{job_id}/process",
    response_model=MalariaAnalysisRead,
)
def process_malaria_analysis_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MalariaAnalysisJob:
    existing = db.query(MalariaAnalysisJob).filter(MalariaAnalysisJob.id == job_id).first()
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job analyse paludisme introuvable.",
        )
    _require_result_access(current_user, existing.result)
    job = process_malaria_job(db, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job analyse paludisme introuvable.",
        )
    return job


@router.get(
    "/malaria/jobs/{job_id}",
    response_model=MalariaAnalysisRead,
)
def get_malaria_analysis_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> MalariaAnalysisJob:
    job = db.query(MalariaAnalysisJob).filter(MalariaAnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job analyse paludisme introuvable.",
        )
    _require_result_access(current_user, job.result)
    return job

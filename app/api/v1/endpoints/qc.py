import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_officer
from app.db.session import get_db
from app.models import QcControl, QcResult, User
from app.schemas.qc import QcControlCreate, QcControlRead, QcResultCreate, QcResultRead
from app.services.westgard import check_westgard

router = APIRouter(prefix="/qc")


@router.get("/controls", response_model=list[QcControlRead])
def list_controls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[QcControl]:
    del current_user
    return (
        db.query(QcControl)
        .filter(QcControl.is_active.is_(True))
        .order_by(QcControl.analyte, QcControl.level)
        .all()
    )


@router.post("/controls", response_model=QcControlRead, status_code=status.HTTP_201_CREATED)
def create_control(
    payload: QcControlCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> QcControl:
    del current_user
    control = QcControl(**payload.model_dump())
    db.add(control)
    db.commit()
    db.refresh(control)
    return control


@router.delete("/controls/{control_id}", status_code=status.HTTP_200_OK)
def deactivate_control(
    control_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> dict[str, str]:
    del current_user
    control = db.query(QcControl).filter(QcControl.id == control_id).first()
    if not control:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contrôle QC introuvable."
        )
    control.is_active = False
    db.commit()
    return {"status": "deactivated"}


@router.get("/controls/{control_id}/results", response_model=list[QcResultRead])
def list_results(
    control_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[QcResult]:
    del current_user
    return (
        db.query(QcResult)
        .filter(QcResult.control_id == control_id)
        .order_by(QcResult.measured_at.asc(), QcResult.id.asc())
        .limit(30)
        .all()
    )


@router.post("/results", response_model=QcResultRead, status_code=status.HTTP_201_CREATED)
def add_result(
    payload: QcResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> QcResult:
    del current_user
    control = db.query(QcControl).filter(QcControl.id == payload.control_id).first()
    if not control:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contrôle QC introuvable."
        )

    # Fetch previous values (up to 9) to evaluate Westgard on up to 10 points
    prev_results = (
        db.query(QcResult)
        .filter(QcResult.control_id == payload.control_id)
        .order_by(QcResult.measured_at.asc(), QcResult.id.asc())
        .all()
    )
    all_values = [r.value for r in prev_results[-9:]] + [payload.value]
    violations = check_westgard(all_values, control.target_mean, control.target_sd)

    result = QcResult(
        control_id=payload.control_id,
        value=payload.value,
        measured_at=payload.measured_at,
        operator=payload.operator,
        violations=json.dumps(violations),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result

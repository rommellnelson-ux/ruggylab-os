from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, Result, Sample, User
from app.schemas.pagination import PaginationMeta, ResultListResponse
from app.schemas.result import ResultCreate, ResultRead
from app.services.inventory import InsufficientStockError, consume_reagents_for_result

router = APIRouter(prefix="/results")


@router.get("", response_model=ResultListResponse)
def list_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sample_id: int | None = Query(default=None, ge=1),
    equipment_id: int | None = Query(default=None, ge=1),
    is_critical: bool | None = Query(default=None),
    is_validated: bool | None = Query(default=None),
) -> ResultListResponse:
    del current_user
    query = db.query(Result)
    if sample_id is not None:
        query = query.filter(Result.sample_id == sample_id)
    if equipment_id is not None:
        query = query.filter(Result.equipment_id == equipment_id)
    if is_critical is not None:
        query = query.filter(Result.is_critical == is_critical)
    if is_validated is not None:
        query = query.filter(Result.is_validated == is_validated)

    total = query.with_entities(func.count(Result.id)).scalar() or 0
    items = query.order_by(Result.id.desc()).offset(skip).limit(limit).all()
    return ResultListResponse(
        items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit)
    )


@router.get("/{result_id}", response_model=ResultRead)
def get_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    del current_user
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resultat introuvable."
        )
    return result


@router.post("", response_model=ResultRead, status_code=status.HTTP_201_CREATED)
def create_result(
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    sample = db.query(Sample).filter(Sample.id == payload.sample_id).first()
    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Echantillon introuvable pour l'identifiant {payload.sample_id}.",
        )

    if payload.equipment_id is not None:
        equipment = (
            db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
        )
        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipement introuvable pour l'identifiant {payload.equipment_id}.",
            )

    result_data = payload.model_dump(exclude_none=True)
    result_data["validator_id"] = current_user.id
    result_data["is_validated"] = True
    result = Result(**result_data)
    db.add(result)
    db.flush()
    try:
        consume_reagents_for_result(
            db,
            result=result,
            user=current_user,
            source="result.create",
        )
    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stock reactif insuffisant pour valider ce resultat.",
                "items": [item.__dict__ for item in exc.items],
            },
        ) from exc
    db.commit()
    db.refresh(result)
    return result

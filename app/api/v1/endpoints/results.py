from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models import Equipment, Result, Sample, User
from app.schemas.fhir import FHIRDiagnosticReport
from app.schemas.pagination import PaginationMeta, ResultListResponse
from app.schemas.result import ResultCreate, ResultRead
from app.services.critical_checker import check_critical
from app.services.delta_checker import check_delta
from app.services.fhir_builder import build_diagnostic_report
from app.services.inventory import InsufficientStockError, consume_reagents_for_result
from app.services.reference_checker import compute_flags
from app.utils.datetime_utils import utcnow_naive

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
        items=[ResultRead.model_validate(r) for r in items],
        meta=PaginationMeta.from_counts(total=total, skip=skip, limit=limit),
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resultat introuvable.")
    return result


@router.get(
    "/{result_id}/fhir",
    response_model=FHIRDiagnosticReport,
    summary="Export NFS result as FHIR R4 DiagnosticReport",
    responses={
        200: {
            "content": {"application/fhir+json": {}},
            "description": "FHIR R4 DiagnosticReport (self-contained, with Patient and Observations)",
        },
        404: {"description": "Result not found"},
    },
)
def get_result_fhir(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONResponse:
    """Return a FHIR R4 DiagnosticReport for the requested result.

    The response is a self-contained FHIR document: the patient resource and
    all CBC Observation resources are embedded as ``contained`` entries so the
    document can be imported into any FHIR server without prior resource
    registration.

    MIME type is ``application/fhir+json`` as required by the FHIR R4 spec.
    """
    del current_user
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resultat introuvable.")

    report = build_diagnostic_report(result)
    return JSONResponse(
        content=report.model_dump(exclude_none=True),
        media_type="application/fhir+json",
    )


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
        equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipement introuvable pour l'identifiant {payload.equipment_id}.",
            )

    result_data = payload.model_dump(exclude_none=True)
    result_data["validator_id"] = current_user.id
    result_data["is_validated"] = True
    # Auto-detect critical values against configured thresholds (OR with manual flag)
    result_data["is_critical"] = payload.is_critical or check_critical(
        payload.data_points, db
    )
    # Resolve patient for delta-check and reference flags
    patient = sample.patient
    patient_id = patient.id if patient else None
    patient_sex = patient.sex if patient else None
    patient_birth = patient.birth_date if patient else None
    # Delta-check: detect abrupt inter-result variation
    delta_exceeded, delta_analytes = check_delta(payload.data_points, patient_id, db)
    result_data["delta_exceeded"] = delta_exceeded
    result_data["delta_analytes"] = delta_analytes if delta_analytes else None
    # Reference flags: HH/H/N/L/LL per analyte
    computed_flags = compute_flags(payload.data_points, patient_sex, patient_birth, db)
    result_data["flags"] = computed_flags if computed_flags else None
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


@router.patch("/{result_id}/ack-critical", response_model=ResultRead)
def ack_critical(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Result:
    """Acknowledge a critical value — records operator and timestamp."""
    result = db.query(Result).filter(Result.id == result_id).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Résultat introuvable."
        )
    if not result.is_critical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce résultat n'est pas marqué critique.",
        )
    if result.critical_ack_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Valeur critique déjà acquittée.",
        )
    result.critical_ack_at = utcnow_naive()
    result.critical_ack_by_id = current_user.id
    db.commit()
    db.refresh(result)
    return result

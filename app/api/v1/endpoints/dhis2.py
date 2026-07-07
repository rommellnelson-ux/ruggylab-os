import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_officer
from app.db.session import get_db
from app.models import Dhis2ExportJob, Dhis2Mapping, User
from app.schemas.dhis2 import (
    Dhis2ExportCreate,
    Dhis2ExportRead,
    Dhis2MappingCreate,
    Dhis2MappingRead,
    Dhis2PreviewRead,
)
from app.services.audit import log_audit_event
from app.services.dhis2_gateway import build_preview, payload_sha256
from app.utils.datetime_utils import utcnow_naive

router = APIRouter(prefix="/integrations/dhis2")


@router.get("/mappings", response_model=list[Dhis2MappingRead])
def list_mappings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Dhis2Mapping]:
    return db.query(Dhis2Mapping).order_by(Dhis2Mapping.internal_code).all()


@router.post(
    "/mappings",
    response_model=Dhis2MappingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_mapping(
    payload: Dhis2MappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dhis2Mapping:
    mapping = Dhis2Mapping(**payload.model_dump())
    db.add(mapping)
    log_audit_event(
        db,
        user=current_user,
        event_type="dhis2.mapping.create",
        entity_type="dhis2_mapping",
        payload={"internal_code": mapping.internal_code},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce mapping existe déjà.") from exc
    db.refresh(mapping)
    return mapping


@router.get("/preview", response_model=Dhis2PreviewRead)
def preview_export(
    period: str,
    data_set_uid: str,
    org_unit_uid: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_officer),
) -> dict:
    try:
        return build_preview(
            db,
            period=period,
            data_set_uid=data_set_uid,
            org_unit_uid=org_unit_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exports", response_model=Dhis2ExportRead, status_code=201)
def create_export(
    payload: Dhis2ExportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> Dhis2ExportJob:
    preview = build_preview(db, **payload.model_dump())
    if preview["warnings"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "Mappings DHIS2 incomplets.", "warnings": preview["warnings"]},
        )
    digest = payload_sha256(preview["payload"])
    existing = (
        db.query(Dhis2ExportJob)
        .filter(
            Dhis2ExportJob.period == payload.period,
            Dhis2ExportJob.data_set_uid == payload.data_set_uid,
            Dhis2ExportJob.org_unit_uid == payload.org_unit_uid,
            Dhis2ExportJob.payload_sha256 == digest,
        )
        .first()
    )
    if existing:
        return existing
    job = Dhis2ExportJob(
        **payload.model_dump(),
        status="CALCULATED",
        payload=preview["payload"],
        payload_sha256=digest,
        created_by_user_id=current_user.id,
    )
    db.add(job)
    db.flush()
    log_audit_event(
        db,
        user=current_user,
        event_type="dhis2.export.create",
        entity_type="dhis2_export",
        entity_id=str(job.id),
        payload={"period": job.period, "payload_sha256": digest},
    )
    db.commit()
    db.refresh(job)
    return job


@router.post("/exports/{export_id}/validate", response_model=Dhis2ExportRead)
def validate_export(
    export_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_officer),
) -> Dhis2ExportJob:
    job = db.query(Dhis2ExportJob).filter(Dhis2ExportJob.id == export_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Export DHIS2 introuvable.")
    if job.status not in {"CALCULATED", "PENDING_REVIEW"}:
        raise HTTPException(status_code=409, detail="Cet export ne peut plus être validé.")
    job.status = "VALIDATED"
    job.validated_by_user_id = current_user.id
    job.validated_at = utcnow_naive()
    log_audit_event(
        db,
        user=current_user,
        event_type="dhis2.export.validate",
        entity_type="dhis2_export",
        entity_id=str(job.id),
        payload={"period": job.period, "payload_sha256": job.payload_sha256},
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("/exports", response_model=list[Dhis2ExportRead])
def list_exports(
    db: Session = Depends(get_db),
    _: User = Depends(require_officer),
) -> list[Dhis2ExportJob]:
    return db.query(Dhis2ExportJob).order_by(Dhis2ExportJob.created_at.desc()).all()


@router.get("/exports/{export_id}.csv")
def export_csv(
    export_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_officer),
) -> Response:
    job = db.query(Dhis2ExportJob).filter(Dhis2ExportJob.id == export_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Export DHIS2 introuvable.")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["dataSet", "period", "orgUnit", "dataElement", "categoryOptionCombo", "value"])
    for item in job.payload.get("dataValues", []):
        writer.writerow(
            [
                job.data_set_uid,
                job.period,
                job.org_unit_uid,
                item["dataElement"],
                item.get("categoryOptionCombo", ""),
                item["value"],
            ]
        )
    return Response(
        stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="dhis2-{job.period}.csv"'},
    )

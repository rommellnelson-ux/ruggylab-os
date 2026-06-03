from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import AuditEvent
from app.schemas.audit_event import AuditEventRead
from app.schemas.pagination import AuditEventListResponse, PaginationMeta

router = APIRouter(prefix="/audit-events")


@router.get("", response_model=AuditEventListResponse, dependencies=[Depends(require_admin)])
def list_audit_events(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> AuditEventListResponse:
    query = db.query(AuditEvent)
    total = query.with_entities(func.count(AuditEvent.id)).scalar() or 0
    items = query.order_by(AuditEvent.id.desc()).offset(skip).limit(limit).all()

    def _to_read(e: AuditEvent) -> AuditEventRead:
        data = AuditEventRead.model_validate(e)
        # Attach username via the ORM relationship (no extra query — already loaded)
        if e.user is not None:
            data = data.model_copy(update={"username": e.user.username})
        return data

    return AuditEventListResponse(
        items=[_to_read(e) for e in items],
        meta=PaginationMeta.from_counts(total=total, skip=skip, limit=limit),
    )

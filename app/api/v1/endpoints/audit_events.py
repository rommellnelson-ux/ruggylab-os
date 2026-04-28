from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import AuditEvent
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
    return AuditEventListResponse(items=items, meta=PaginationMeta(total=total, skip=skip, limit=limit))

import csv
import datetime as dt
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import AuditEvent, User
from app.schemas.audit_event import AuditEventRead
from app.schemas.pagination import AuditEventListResponse, PaginationMeta
from app.utils.csv_safety import sanitize_csv_cell

router = APIRouter(prefix="/audit-events")


def _apply_filters(
    query: Any,
    *,
    event_type: str | None,
    entity_type: str | None,
    username: str | None,
    date_from: dt.date | None,
    date_to: dt.date | None,
    db: Session,
) -> Any:
    """Applique les filtres optionnels communs (liste + export)."""
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if username:
        user = db.query(User).filter(User.username == username).first()
        # -1 ne correspond à aucun id → renvoie un ensemble vide proprement
        query = query.filter(AuditEvent.user_id == (user.id if user else -1))
    if date_from:
        query = query.filter(AuditEvent.created_at >= dt.datetime.combine(date_from, dt.time.min))
    if date_to:
        query = query.filter(AuditEvent.created_at <= dt.datetime.combine(date_to, dt.time.max))
    return query


@router.get("", response_model=AuditEventListResponse, dependencies=[Depends(require_admin)])
def list_audit_events(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    username: str | None = Query(default=None),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
) -> AuditEventListResponse:
    query = _apply_filters(
        db.query(AuditEvent),
        event_type=event_type,
        entity_type=entity_type,
        username=username,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )
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


@router.get("/export.csv", dependencies=[Depends(require_admin)])
def export_audit_events_csv(
    db: Session = Depends(get_db),
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    username: str | None = Query(default=None),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
) -> Response:
    """Export CSV du journal d'audit (filtres identiques à la liste). Réservé admin."""
    query = _apply_filters(
        db.query(AuditEvent),
        event_type=event_type,
        entity_type=entity_type,
        username=username,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )
    events = query.order_by(AuditEvent.id.desc()).limit(limit).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["id", "created_at", "username", "event_type", "entity_type", "entity_id", "payload"]
    )
    for e in events:
        writer.writerow(
            [
                sanitize_csv_cell(x)
                for x in (
                    e.id,
                    e.created_at.isoformat() if e.created_at else "",
                    e.user.username if e.user else "",
                    e.event_type,
                    e.entity_type,
                    e.entity_id or "",
                    (e.payload or "").replace("\n", " "),
                )
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-export.csv"'},
    )

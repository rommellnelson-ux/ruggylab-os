import json

from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def log_audit_event(
    db: Session,
    *,
    user: User | None,
    event_type: str,
    entity_type: str,
    entity_id: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user.id if user else None,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=json.dumps(payload, ensure_ascii=True) if payload is not None else None,
    )
    db.add(event)
    return event

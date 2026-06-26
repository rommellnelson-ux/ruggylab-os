import datetime
import json

from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def _json_default(obj: object) -> str:
    """Fallback serialiser for types not handled by the stdlib json encoder."""
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


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
        payload=json.dumps(payload, ensure_ascii=True, default=_json_default)
        if payload is not None
        else None,
    )
    db.add(event)
    return event

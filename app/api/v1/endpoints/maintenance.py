"""Admin maintenance endpoints.

These endpoints require administrator role and perform housekeeping
operations that are safe to expose as HTTP calls (e.g. for cron triggers
or Kubernetes CronJob health-check integration).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.services.token_cleanup import purge_expired_tokens

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.delete(
    "/refresh-tokens/expired",
    summary="Purge expired refresh tokens",
    responses={200: {"description": "Rows deleted"}},
)
def cleanup_expired_tokens(
    keep_days: int = Query(
        default=7,
        ge=0,
        le=365,
        description="Grace period: tokens that expired more than this many days ago are deleted.",
    ),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Delete refresh tokens that expired more than ``keep_days`` days ago.

    This endpoint is idempotent — calling it multiple times produces the
    same result (all stale tokens removed).  It is safe to call from a
    scheduler or manually from an admin console.

    Only tokens past their ``expires_at`` date (plus the keep_days grace
    period) are removed.  Active tokens are never affected.
    """
    deleted = purge_expired_tokens(db, keep_days=keep_days)
    return {"deleted": deleted, "keep_days": keep_days}

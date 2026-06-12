"""Refresh-token table housekeeping.

Expired and revoked tokens accumulate in the ``refresh_tokens`` table over
time.  This module provides a service function that prunes those rows, plus
an async loop that runs periodically inside the app's lifespan.

The cleanup criteria are intentionally conservative:
- Tokens that expired MORE THAN ``keep_days`` ago are deleted.
- Tokens that were revoked AND expired are deleted.
- Active, non-expired tokens are NEVER touched.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import RefreshToken, RevokedToken
from app.utils.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Default: keep rows for 7 days past their expiry before deleting them.
# This provides a short audit window in case of incident investigation.
_DEFAULT_KEEP_DAYS = 7


def purge_expired_tokens(db: Session, *, keep_days: int = _DEFAULT_KEEP_DAYS) -> int:
    """Delete stale refresh tokens from the database.

    A token is eligible for deletion when it expired more than ``keep_days``
    days ago, regardless of whether it was revoked.

    Args:
        db: Active SQLAlchemy session.
        keep_days: Grace period in days past expiry before a row is removed.

    Returns:
        Number of rows deleted.
    """
    import datetime

    cutoff = utcnow_naive() - datetime.timedelta(days=keep_days)
    deleted = (
        db.query(RefreshToken)
        .filter(RefreshToken.expires_at < cutoff)
        .delete(synchronize_session=False)
    )
    # Purge également la denylist des jetons d'accès expirés (plus besoin de les
    # mémoriser une fois la date d'expiration dépassée).
    deleted_revoked = (
        db.query(RevokedToken)
        .filter(RevokedToken.expires_at < utcnow_naive())
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info(
        "token_cleanup: deleted %d stale refresh token(s), %d expired revocation(s)",
        deleted,
        deleted_revoked,
    )
    return deleted


async def periodic_token_cleanup(
    interval_seconds: int = 3600,
    keep_days: int = _DEFAULT_KEEP_DAYS,
) -> None:
    """Async loop that purges stale refresh tokens every ``interval_seconds``.

    Designed to run as a background task inside the FastAPI lifespan
    (``asyncio.create_task``).  Errors are caught and logged so a transient
    DB hiccup does not crash the background loop.

    Args:
        interval_seconds: How often to run the cleanup (default: 1 hour).
        keep_days: Grace period passed through to ``purge_expired_tokens``.
    """
    logger.info(
        "token_cleanup: background task started (interval=%ds, keep_days=%d)",
        interval_seconds,
        keep_days,
    )
    while True:
        await asyncio.sleep(interval_seconds)
        db = SessionLocal()
        try:
            purge_expired_tokens(db, keep_days=keep_days)
        except Exception as exc:  # pragma: no cover — transient DB errors
            logger.warning("token_cleanup: unexpected error: %s", exc)
        finally:
            db.close()

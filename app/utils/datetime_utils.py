"""Shared datetime utilities for RuggyLab OS.

All timestamps stored in the database are naive UTC datetimes (no tzinfo),
consistent with SQLite/PostgreSQL DateTime columns without timezone support.
Use utcnow_naive() everywhere a current timestamp is needed for DB persistence.
"""

import datetime as dt


def utcnow_naive() -> dt.datetime:
    """Return the current UTC time as a naive datetime (tzinfo stripped).

    SQLAlchemy DateTime columns (without timezone=True) expect naive datetimes.
    This helper ensures a consistent, correct source of time across the codebase.
    """
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)

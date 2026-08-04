"""Régression concurrente R5 nécessitant PostgreSQL réel."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest

from app.api.v1.endpoints.samples import _next_lab_number
from app.db.session import SessionLocal, engine
from app.models import Sample

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Ce test valide le verrou transactionnel sous PostgreSQL.",
)


def _sequence(lab_number: str) -> int:
    return int(lab_number.rsplit("-", maxsplit=1)[1])


def test_r5_concurrent_generation_waits_for_committed_sequence() -> None:
    suffix = uuid.uuid4().hex[:12]
    first_barcode = f"R5-PG-FIRST-{suffix}"
    second_barcode = f"R5-PG-SECOND-{suffix}"
    second_started = threading.Event()
    first = SessionLocal()
    executor = ThreadPoolExecutor(max_workers=1)

    def allocate_second() -> str:
        with SessionLocal() as second:
            second_started.set()
            number = _next_lab_number(second)
            second.add(Sample(barcode=second_barcode, lab_number=number, status="Recu"))
            second.commit()
            return number

    try:
        first_number = _next_lab_number(first)
        first.add(Sample(barcode=first_barcode, lab_number=first_number, status="Recu"))

        pending = executor.submit(allocate_second)
        assert second_started.wait(timeout=5)
        with pytest.raises(FutureTimeoutError):
            pending.result(timeout=0.25)

        first.commit()
        second_number = pending.result(timeout=10)

        assert _sequence(second_number) == _sequence(first_number) + 1
    finally:
        first.rollback()
        first.close()
        executor.shutdown(wait=True, cancel_futures=True)
        with SessionLocal() as cleanup:
            cleanup.query(Sample).filter(
                Sample.barcode.in_([first_barcode, second_barcode])
            ).delete(synchronize_session=False)
            cleanup.commit()

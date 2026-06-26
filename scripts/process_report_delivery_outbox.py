"""Traite la file de diffusion des comptes-rendus RuggyLab.

Usage ponctuel:
    python scripts/process_report_delivery_outbox.py

Usage service/tache planifiee:
    python scripts/process_report_delivery_outbox.py --limit 100
"""

from __future__ import annotations

import argparse
import logging
import time

from app.db.session import SessionLocal
from app.services.report_delivery_outbox import process_report_delivery_outbox


logger = logging.getLogger("ruggylab.report_delivery_outbox")


def _run_once(limit: int, max_attempts: int) -> None:
    db = SessionLocal()
    try:
        result = process_report_delivery_outbox(
            db,
            limit=limit,
            max_attempts=max_attempts,
        )
        logger.info(
            "report outbox processed=%s retried=%s dead_lettered=%s skipped=%s",
            result.processed,
            result.retried,
            result.dead_lettered,
            result.skipped,
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process RuggyLab report delivery outbox")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        _run_once(limit=args.limit, max_attempts=args.max_attempts)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

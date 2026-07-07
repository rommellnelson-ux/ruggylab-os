"""Traite la file de diffusion des comptes-rendus RuggyLab.

Usage ponctuel:
    python scripts/process_report_delivery_outbox.py

Usage service/tache planifiee:
    python scripts/process_report_delivery_outbox.py --limit 100
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.report_delivery_outbox import process_report_delivery_outbox  # noqa: E402


logger = logging.getLogger("ruggylab.report_delivery_outbox")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("la valeur doit etre strictement positive")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("la valeur doit etre strictement positive")
    return parsed


def _configure_logging(log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def _check_database() -> None:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    logger.info("report outbox check=ok database=reachable")


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process RuggyLab report delivery outbox")
    parser.add_argument("--limit", type=positive_int, default=50)
    parser.add_argument("--max-attempts", type=positive_int, default=8)
    parser.add_argument("--interval", type=positive_float, default=30.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifie la connexion a la base sans consommer la file.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Ajoute les journaux dans ce fichier (le dossier est cree si necessaire).",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_file)
    if args.check:
        _check_database()
        return 0
    try:
        while True:
            _run_once(limit=args.limit, max_attempts=args.max_attempts)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("report outbox worker stopped")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    finally:
        engine.dispose()
        logging.shutdown()
    raise SystemExit(exit_code)

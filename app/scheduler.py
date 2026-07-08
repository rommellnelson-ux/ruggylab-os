"""Entrypoint du process planificateur (rôle ``scheduler``).

Exécute les tâches planifiées en **un seul exemplaire**, séparé des workers web,
afin d'éviter les duplications en multi-worker (cf. ``settings.PROCESS_ROLE``).

Lancement : ``python -m app.scheduler`` (même image Docker que le web).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.services.token_cleanup import periodic_token_cleanup

logger = logging.getLogger(__name__)


async def _heartbeat_loop(path: str, interval_seconds: int = 30) -> None:
    """Écrit un horodatage régulier pour que le healthcheck compose atteste la vie.

    La tâche principale (purge des jetons) ne s'exécute qu'une fois par heure ; un
    healthcheck qui l'attendrait signalerait le process comme mort entre-temps.
    Ce battement découplé permet une sonde de fraîcheur (< 2 min).
    """
    hb = Path(path)
    while True:
        with contextlib.suppress(OSError):
            hb.write_text(str(int(time.time())), encoding="ascii")
        await asyncio.sleep(interval_seconds)


async def _run() -> None:
    configure_logging(level="INFO", json_logs=not settings.TESTING, log_file=None)
    logger.info("Scheduler process starting (role=%s)", settings.PROCESS_ROLE)
    heartbeat = asyncio.create_task(_heartbeat_loop(settings.SCHEDULER_HEARTBEAT_FILE))
    try:
        # Boucle infinie ; ajouter ici les autres tâches planifiées à l'avenir.
        await periodic_token_cleanup(interval_seconds=3600, keep_days=7)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

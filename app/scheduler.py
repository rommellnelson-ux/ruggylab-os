"""Entrypoint du process planificateur (rôle ``scheduler``).

Exécute les tâches planifiées en **un seul exemplaire**, séparé des workers web,
afin d'éviter les duplications en multi-worker (cf. ``settings.PROCESS_ROLE``).

Lancement : ``python -m app.scheduler`` (même image Docker que le web).
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.services.token_cleanup import periodic_token_cleanup

logger = logging.getLogger(__name__)


async def _run() -> None:
    configure_logging(level="INFO", json_logs=not settings.TESTING, log_file=None)
    logger.info("Scheduler process starting (role=%s)", settings.PROCESS_ROLE)
    # Boucle infinie ; ajouter ici les autres tâches planifiées à l'avenir.
    await periodic_token_cleanup(interval_seconds=3600, keep_days=7)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

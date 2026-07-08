"""Entrypoint de la passerelle automates (rôle ``analyzer-gateway``).

Exécute le listener DH36 en **un seul exemplaire** : il bind un port TCP, donc
plusieurs workers web se le disputeraient. Isolé ici, séparé du web.

Lancement : ``python -m app.analyzer_gateway`` (même image Docker que le web).
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.services.interfacing.listener_dh36 import DH36Listener

logger = logging.getLogger(__name__)


async def _run() -> None:
    configure_logging(level="INFO", json_logs=not settings.TESTING, log_file=None)
    listener = DH36Listener(
        host=settings.DH36_LISTENER_HOST,
        port=settings.DH36_LISTENER_PORT,
    )
    logger.info(
        "Analyzer gateway starting: DH36 listener on %s:%s",
        settings.DH36_LISTENER_HOST,
        settings.DH36_LISTENER_PORT,
    )
    await listener.start()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

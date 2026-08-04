"""Entrypoint de la passerelle automates (rôle ``analyzer-gateway``).

Exécute en **un seul exemplaire** les listeners TCP qui bindent un port (donc
que plusieurs workers web se disputeraient) :

- le listener DH36 historique (MLLP -> ingestion BDD directe) ;
- le listener brut « aveugle » (trames archivées telles quelles dans Redis,
  cf. ``app.services.interfacing.raw_tcp_listener``) — filet de sécurité en
  attendant le manuel d'interfaçage du Dymind DH36.

Si un listener meurt, le process s'arrête : c'est l'orchestrateur (politique
``restart`` de docker-compose) qui relance, plutôt qu'un process zombie qui
n'écoute plus qu'à moitié.

Lancement : ``python -m app.analyzer_gateway`` (même image Docker que le web).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def _heartbeat_loop(path: str, interval_seconds: int = 30) -> None:
    """Atteste la vie du process même si toutes les interfaces sont désactivées."""
    heartbeat = Path(path)
    while True:
        with contextlib.suppress(OSError):
            heartbeat.write_text(str(int(time.time())), encoding="ascii")
        await asyncio.sleep(interval_seconds)


async def _run() -> None:
    configure_logging(level="INFO", json_logs=not settings.TESTING, log_file=None)
    tasks: list[asyncio.Task[None]] = []

    if settings.ENABLE_DH36_LISTENER:
        from app.services.interfacing.listener_dh36 import DH36Listener

        dh36 = DH36Listener(
            host=settings.DH36_LISTENER_HOST,
            port=settings.DH36_LISTENER_PORT,
        )
        logger.info(
            "Analyzer gateway: DH36 listener on %s:%s",
            settings.DH36_LISTENER_HOST,
            settings.DH36_LISTENER_PORT,
        )
        tasks.append(asyncio.create_task(dh36.start(), name="dh36-listener"))
    else:
        logger.info("Listener DH36 désactivé (ENABLE_DH36_LISTENER=false).")

    if settings.ANALYZER_RAW_LISTENER_ENABLED:
        if settings.REDIS_URL:
            from app.services.analyzers.registry import enabled_bindings
            from app.services.interfacing.raw_tcp_listener import RawAnalyzerTCPListener

            for binding in enabled_bindings(settings):
                listener = RawAnalyzerTCPListener(
                    host=binding.host,
                    port=binding.port,
                    redis_url=settings.REDIS_URL,
                    analyzer_kind=binding.kind.value,
                    allowed_ips=binding.allowed_ips,
                    queue_key=settings.ANALYZER_RAW_QUEUE_KEY,
                    queue_maxlen=settings.ANALYZER_RAW_QUEUE_MAXLEN,
                    ack_mode=binding.ack_mode,
                    max_frame_bytes=settings.ANALYZER_RAW_MAX_FRAME_BYTES,
                    idle_timeout_seconds=settings.ANALYZER_RAW_IDLE_TIMEOUT_SECONDS,
                )
                logger.info(
                    "Analyzer gateway: listener [%s] on %s:%s -> Redis %s",
                    binding.kind.value,
                    binding.host,
                    binding.port,
                    settings.ANALYZER_RAW_QUEUE_KEY,
                )
                tasks.append(
                    asyncio.create_task(listener.start(), name=f"raw-listener-{binding.kind.value}")
                )
        else:
            logger.warning(
                "Listeners TCP bruts NON démarrés : REDIS_URL absent alors que le filet "
                "de sécurité Redis est requis (ANALYZER_RAW_LISTENER_ENABLED=true)."
            )

    listener_count = len(tasks)
    if listener_count == 0:
        logger.warning(
            "Analyzer gateway: aucune interface qualifiée ; process vivant en mode désactivé."
        )

    tasks.append(
        asyncio.create_task(
            _heartbeat_loop(settings.ANALYZER_GATEWAY_HEARTBEAT_FILE),
            name="analyzer-gateway-heartbeat",
        )
    )

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for task in pending:
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.gather(*pending)
    for task in done:
        exc = task.exception()
        if exc is not None:
            logger.error("Listener %s arrêté sur erreur: %s", task.get_name(), exc)
            raise exc


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

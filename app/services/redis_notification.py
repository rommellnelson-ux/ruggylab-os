"""Fan-out Redis pub/sub des notifications temps-réel (multi-worker).

Quand ``REDIS_URL`` est configuré, les événements d'alerte publiés sur un worker
sont diffusés à tous les autres via un canal Redis, afin que chaque connexion
WebSocket — quel que soit le worker qui la sert — reçoive le push immédiat.

Mono-processus (sans Redis) : ce module n'est pas activé, le bus in-process
suffit. Activation depuis le lifespan de l'application.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from app.services.notification_bus import inject_remote_event, set_redis_publisher

logger = logging.getLogger(__name__)

NOTIF_CHANNEL = "ruggylab:notifications"


def make_redis_publisher(loop: asyncio.AbstractEventLoop, client: Any) -> Callable[[dict], None]:
    """Construit une fonction sync qui publie un événement sur Redis.

    Sûre à appeler depuis un thread de requête : planifie la coroutine de
    publication sur la boucle principale via ``run_coroutine_threadsafe``.
    """

    def _publish(event: dict) -> None:
        try:
            payload = json.dumps(event)
        except (TypeError, ValueError):
            return
        try:
            asyncio.run_coroutine_threadsafe(client.publish(NOTIF_CHANNEL, payload), loop)
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis notif publish failed: %s", exc)

    return _publish


async def redis_subscriber_loop(client: Any) -> None:
    """Boucle d'abonnement : réinjecte localement les événements distants.

    Conçue pour tourner comme tâche de fond dans le lifespan FastAPI.
    """
    pubsub = client.pubsub()
    await pubsub.subscribe(NOTIF_CHANNEL)
    logger.info("redis notif subscriber: abonné au canal %s", NOTIF_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            try:
                event = json.loads(data)
            except (TypeError, ValueError):
                continue
            inject_remote_event(event)
    except asyncio.CancelledError:  # pragma: no cover — arrêt propre
        raise
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        logger.warning("redis notif subscriber stopped: %s", exc)
    finally:
        with __import__("contextlib").suppress(Exception):
            await pubsub.unsubscribe(NOTIF_CHANNEL)


def enable_redis_fanout(loop: asyncio.AbstractEventLoop, client: Any) -> None:
    """Active le publisher Redis sur le bus de notifications."""
    set_redis_publisher(make_redis_publisher(loop, client))


def disable_redis_fanout() -> None:
    set_redis_publisher(None)

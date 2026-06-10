"""Bus de notifications en mémoire (in-process) pour push WebSocket événementiel.

Permet de pousser un instantané d'alertes immédiatement lorsqu'un événement
significatif survient (nouvelle valeur critique, delta dépassé), au lieu
d'attendre le prochain cycle de sondage.

Architecture : un ``asyncio.Queue`` par connexion WebSocket abonnée. ``publish``
réveille tous les abonnés. Mono-processus ; pour le multi-worker, brancher un
publish/subscribe Redis sur ``publish`` / un consommateur dédié (point
d'extension documenté).
"""
from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable

# Identifiant unique de ce processus/worker — permet d'ignorer l'écho de ses
# propres messages quand le fan-out Redis est actif (évite les doublons).
WORKER_ID = uuid.uuid4().hex


class NotificationBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict | None = None) -> None:
        """Notifie tous les abonnés (non bloquant ; ignore les files pleines)."""
        payload = event or {"type": "event"}
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Instance partagée par le processus.
bus = NotificationBus()

# Éditeur Redis optionnel (fan-out multi-worker). None = mono-processus.
# Une fonction sync qui accepte un dict d'événement et le publie sur Redis.
_redis_publisher: Callable[[dict], None] | None = None


def set_redis_publisher(publisher: Callable[[dict], None] | None) -> None:
    """Active (ou désactive avec None) le fan-out Redis des événements."""
    global _redis_publisher
    _redis_publisher = publisher


def inject_remote_event(event: dict) -> None:
    """Injecte localement un événement reçu d'un autre worker (via Redis).

    Ignore les messages émis par ce worker (écho) pour éviter les doublons.
    """
    if event.get("_origin") == WORKER_ID:
        return
    local = {k: v for k, v in event.items() if k != "_origin"}
    bus.publish(local)


def publish_alert_event(event_type: str, **fields: object) -> None:
    """Publie un événement d'alerte (best-effort, jamais bloquant).

    - Diffusion locale immédiate (abonnés WebSocket de ce worker).
    - Si le fan-out Redis est actif, diffusion aux autres workers (tagguée
      avec l'identifiant de ce worker pour ignorer l'écho).
    """
    event = {"type": event_type, **fields}
    try:
        bus.publish(event)
    except Exception:  # noqa: BLE001 — la notification ne doit jamais casser l'appelant
        pass
    if _redis_publisher is not None:
        try:
            _redis_publisher({**event, "_origin": WORKER_ID})
        except Exception:  # noqa: BLE001
            pass

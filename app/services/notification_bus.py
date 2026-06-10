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


def publish_alert_event(event_type: str, **fields: object) -> None:
    """Publie un événement d'alerte sur le bus (best-effort, jamais bloquant).

    Sûr à appeler depuis du code synchrone (endpoints) : si une boucle asyncio
    tourne, ``put_nowait`` fonctionne ; sinon l'appel est simplement ignoré.
    """
    try:
        bus.publish({"type": event_type, **fields})
    except Exception:  # noqa: BLE001 — la notification ne doit jamais casser l'appelant
        pass

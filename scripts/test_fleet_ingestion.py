#!/usr/bin/env python3
r"""Test d'intégration : routage port -> Redis de la flotte d'automates.

Prouve que le ``analyzer-gateway`` multi-listeners range chaque trame dans
``raw_analyzer_frames`` avec le bon discriminateur ``analyzer_kind``, en
envoyant **simultanément** (``asyncio.gather``) des trames sur les 3 ports :

    9000  hématologie   (Dymind DH36)      -> analyzer_kind=dymind_hematology
    9001  biochimie     (Dymind)           -> analyzer_kind=dymind_biochemistry
    9002  immuno        (Anbio Bioscann)   -> analyzer_kind=anbio_immuno

Autonome : si ``REDIS_URL`` est défini dans l'environnement, on l'utilise ;
sinon un mini-serveur Redis RESP en mémoire est démarré (la machine de dev n'a
pas forcément Redis). La relecture se fait via un vrai client ``redis.asyncio``
(LRANGE) pour exercer le chemin complet.

Usage :
    python scripts/test_fleet_ingestion.py
    python scripts/test_fleet_ingestion.py --frames 10
    REDIS_URL=redis://localhost:6379/0 python scripts/test_fleet_ingestion.py
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
import sys

import redis.asyncio as aioredis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.analyzers.registry import AnalyzerKind  # noqa: E402
from app.services.interfacing.raw_tcp_listener import RawAnalyzerTCPListener  # noqa: E402

logger = logging.getLogger("test_fleet_ingestion")

QUEUE_KEY = "raw_analyzer_frames_fleet_test"

# Un port par automate, avec une trame factice minimale (délimiteur inclus).
FLEET: dict[AnalyzerKind, tuple[int, bytes]] = {
    AnalyzerKind.HEMATOLOGY: (
        9000,
        b"\x0bMSH|^~\\&|DH36|DYMIND|HEMATO|LAB||ORU^R01|1||2.3.1\r\x1c\x0d",
    ),
    AnalyzerKind.BIOCHEMISTRY: (9001, b"\x021H|\\^&|||DYMIND-BIO|||||||P|E1394-97\x03B4\r\n\x04"),
    AnalyzerKind.IMMUNO: (9002, b"\x021H|\\^&|||ANBIO-IMMUNO|||||||P|E1394-97\x03C2\r\n\x04"),
}


# ── Mini-serveur Redis RESP en mémoire (repli sans Redis réel) ────────────────


class _FakeRedisServer:
    """Sous-ensemble RESP2 suffisant pour LPUSH/LRANGE/LTRIM/LLEN/DEL/PING."""

    def __init__(self) -> None:
        self.store: dict[str, list[bytes]] = {}
        self._server: asyncio.Server | None = None

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self._server = await asyncio.start_server(self._handle, host, port)
        return int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readline()
                if not header:
                    break
                if not header.startswith(b"*"):
                    writer.write(b"+OK\r\n")
                    await writer.drain()
                    continue
                args: list[bytes] = []
                for _ in range(int(header[1:].strip())):
                    length = int((await reader.readline())[1:].strip())
                    args.append((await reader.readexactly(length + 2))[:-2])
                writer.write(self._dispatch(args))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    def _dispatch(self, args: list[bytes]) -> bytes:
        cmd = args[0].upper()
        if cmd == b"LPUSH":
            key = args[1].decode()
            lst = self.store.setdefault(key, [])
            for item in args[2:]:
                lst.insert(0, item)
            return f":{len(lst)}\r\n".encode()
        if cmd == b"LLEN":
            return f":{len(self.store.get(args[1].decode(), []))}\r\n".encode()
        if cmd == b"LRANGE":
            lst = self.store.get(args[1].decode(), [])
            start, stop = int(args[2]), int(args[3])
            sliced = lst[start:] if stop == -1 else lst[start : stop + 1]
            out = f"*{len(sliced)}\r\n".encode()
            for item in sliced:
                out += f"${len(item)}\r\n".encode() + item + b"\r\n"
            return out
        if cmd == b"DEL":
            existed = 0
            for key in args[1:]:
                existed += 1 if self.store.pop(key.decode(), None) is not None else 0
            return f":{existed}\r\n".encode()
        if cmd in (b"LTRIM", b"PING", b"HELLO", b"CLIENT"):
            return b"+OK\r\n"
        return b"+OK\r\n"


# ── Envoi simultané ──────────────────────────────────────────────────────────


async def _send(host: str, port: int, frame: bytes, frames: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        for _ in range(frames):
            writer.write(frame)
            await writer.drain()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(reader.read(8), timeout=1.0)  # ACK éventuel
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def run(args: argparse.Namespace) -> int:
    host = "127.0.0.1"
    fake: _FakeRedisServer | None = None
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        logger.info("Utilisation de REDIS_URL=%s", redis_url)
    else:
        fake = _FakeRedisServer()
        redis_port = await fake.start(host)
        redis_url = f"redis://{host}:{redis_port}/0"
        logger.info("Mini-Redis RESP démarré sur %s (pas de Redis réel détecté)", redis_url)

    client = aioredis.from_url(redis_url, decode_responses=False)
    await client.delete(QUEUE_KEY)

    # Un listener par automate (routage par port).
    listeners: list[RawAnalyzerTCPListener] = [
        RawAnalyzerTCPListener(
            host=host,
            port=port,
            redis_url=redis_url,
            analyzer_kind=kind.value,
            queue_key=QUEUE_KEY,
            ack_mode="ack",
            idle_timeout_seconds=10.0,
        )
        for kind, (port, _frame) in FLEET.items()
    ]
    server_tasks = [asyncio.create_task(listener.start()) for listener in listeners]
    await asyncio.sleep(0.4)  # laisser les serveurs bind

    # Envoi SIMULTANÉ sur les 3 ports.
    await asyncio.gather(
        *[_send(host, port, frame, args.frames) for _port, (port, frame) in FLEET.items()]
    )

    expected_total = len(FLEET) * args.frames
    for _ in range(50):
        if await client.llen(QUEUE_KEY) >= expected_total:
            break
        await asyncio.sleep(0.1)

    raw_items = await client.lrange(QUEUE_KEY, 0, -1)
    docs = [json.loads(item) for item in raw_items]

    # Arrêt propre.
    for task in server_tasks:
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.gather(*server_tasks)
    for listener in listeners:
        await listener.stop()
    await client.aclose()
    if fake is not None:
        await fake.stop()

    return _assert_routing(docs, args.frames)


def _assert_routing(docs: list[dict], frames_per_port: int) -> int:
    """Vérifie le routage port -> analyzer_kind et l'intégrité des trames."""
    ok = True
    expected_total = len(FLEET) * frames_per_port
    if len(docs) != expected_total:
        logger.error("Total trames: attendu %d, obtenu %d", expected_total, len(docs))
        ok = False

    port_by_kind = {kind.value: port for kind, (port, _f) in FLEET.items()}
    expected_frame = {kind.value: frame for kind, (_p, frame) in FLEET.items()}

    for kind, (port, frame) in ((k.value, v) for k, v in FLEET.items()):
        matching = [d for d in docs if d["analyzer_kind"] == kind]
        if len(matching) != frames_per_port:
            logger.error("[%s] attendu %d trames, obtenu %d", kind, frames_per_port, len(matching))
            ok = False
        for doc in matching:
            checks = {
                "port": doc["port"] == port,
                "sha256": doc["sha256"] == hashlib.sha256(frame).hexdigest(),
                "b64": base64.b64decode(doc["frame_b64"]) == frame,
                "raw_payload": doc["raw_payload"] == frame.decode("utf-8", errors="replace"),
                "keys": {"timestamp", "source_ip", "port", "raw_payload"} <= doc.keys(),
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                logger.error("[%s] trame invalide, échecs=%s", kind, failed)
                ok = False

    # Aucune fuite inter-ports : chaque kind n'a que sa propre trame.
    for doc in docs:
        kind = doc["analyzer_kind"]
        if doc["raw_payload"] != expected_frame[kind].decode("utf-8", errors="replace"):
            logger.error("[%s] contenu routé depuis le mauvais port %s", kind, doc["port"])
            ok = False
        if doc["port"] != port_by_kind[kind]:
            logger.error("[%s] port %s incohérent avec le kind", kind, doc["port"])
            ok = False

    if ok:
        logger.info(
            "OK : %d trames routées correctement sur %d automates (%s).",
            len(docs),
            len(FLEET),
            ", ".join(k.value for k in FLEET),
        )
    return 0 if ok else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--frames", type=int, default=5, help="Nombre de trames envoyées par automate"
    )
    parser.add_argument("--verbose", action="store_true", help="Logs DEBUG")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

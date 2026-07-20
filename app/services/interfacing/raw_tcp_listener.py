r"""Listener TCP « aveugle » de la passerelle automates (filet de sécurité).

En attendant le manuel d'interfaçage du Dymind DH36 (HL7 ou ASTM ?), ce
listener n'interprète PAS les trames : il les pousse telles quelles dans une
liste Redis (``LPUSH raw_analyzer_frames``), horodatées et annotées de l'IP
source, pour rejeu ultérieur par le futur parseur
(cf. ``app.services.analyzers.base``).

Découpage sans connaître le protocole : on repère les terminateurs usuels des
deux candidats — fin de bloc MLLP (HL7) ``\x1c\x0d`` et EOT ASTM ``\x04`` —
et on vide le reliquat à la déconnexion (``eof-flush``) ou en cas de trame
anormalement longue (``overflow-flush``). La trame est stockée en base64
(fidélité octet à octet), doublée d'un aperçu lisible et d'un SHA-256.

Résilience :
- coupure brutale de socket → loggée, la connexion est nettoyée, le serveur
  continue ;
- Redis indisponible → la trame part dans un tampon mémoire borné, rejoué au
  prochain push réussi ; la perte (tampon plein) est loggée en erreur ;
- client bavard sans délimiteur → flush forcé au-delà de
  ``max_frame_bytes`` (pas d'accumulation mémoire illimitée).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime as dt
import hashlib
import json
import logging
from collections import deque
from collections.abc import Awaitable
from typing import cast

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

ASCII_ACK = b"\x06"
ASTM_EOT = b"\x04"
MLLP_END_BLOCK = b"\x1c\x0d"

# Terminateurs reconnus pour borner une trame, avec l'indice de protocole
# correspondant (simple indice pour le futur parseur — rien n'est parsé ici).
_DELIMITERS: tuple[tuple[bytes, str], ...] = (
    (MLLP_END_BLOCK, "mllp-end"),
    (ASTM_EOT, "astm-eot"),
)


def split_frames(buffer: bytes) -> tuple[list[tuple[bytes, str]], bytes]:
    """Découpe ``buffer`` sur les terminateurs connus (MLLP, ASTM EOT).

    Retourne les trames complètes (terminateur inclus) accompagnées de
    l'indice du délimiteur rencontré, puis le reliquat encore incomplet.
    """
    frames: list[tuple[bytes, str]] = []
    while True:
        best: tuple[int, bytes, str] | None = None
        for delimiter, hint in _DELIMITERS:
            idx = buffer.find(delimiter)
            if idx != -1 and (best is None or idx < best[0]):
                best = (idx, delimiter, hint)
        if best is None:
            return frames, buffer
        idx, delimiter, hint = best
        end = idx + len(delimiter)
        frames.append((buffer[:end], hint))
        buffer = buffer[end:]


def build_frame_payload(
    frame: bytes,
    *,
    analyzer_kind: str,
    listener_port: int,
    delimiter_hint: str,
    source_ip: str,
    source_port: int,
) -> str:
    """Sérialise une trame brute en document JSON auto-portant pour Redis.

    ``analyzer_kind`` est le discriminateur de routage (port -> automate) que
    ``AnalyzerParserFactory`` utilisera plus tard pour choisir le parseur.
    ``raw_payload`` est le décodage best-effort de la trame ; ``frame_b64``
    garantit la fidélité octet à octet (trames binaires / caractères de
    contrôle ASTM).
    """
    return json.dumps(
        {
            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            "analyzer_kind": analyzer_kind,
            "source_ip": source_ip,
            "source_port": source_port,
            "port": listener_port,
            "delimiter": delimiter_hint,
            "bytes": len(frame),
            "sha256": hashlib.sha256(frame).hexdigest(),
            "raw_payload": frame.decode("utf-8", errors="replace"),
            "frame_b64": base64.b64encode(frame).decode("ascii"),
        },
        ensure_ascii=True,
    )


class RawAnalyzerTCPListener:
    """Serveur TCP asynchrone qui archive les trames brutes dans Redis."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        redis_url: str,
        analyzer_kind: str = "unknown",
        allowed_ips: list[str] | None = None,
        queue_key: str = "raw_analyzer_frames",
        queue_maxlen: int = 100_000,
        ack_mode: str = "ack",
        max_frame_bytes: int = 1_048_576,
        idle_timeout_seconds: float = 300.0,
        retry_buffer_maxlen: int = 1_000,
    ) -> None:
        if ack_mode not in ("ack", "silent", "close"):
            raise ValueError(f"ack_mode invalide: {ack_mode!r} (attendu: ack|silent|close)")
        self.host = host
        self.port = port
        self.redis_url = redis_url
        self.analyzer_kind = analyzer_kind
        # Allowlist de sécurité (VLAN) : vide = on s'en remet au firewall.
        self.allowed_ips = set(allowed_ips or [])
        self.queue_key = queue_key
        self.queue_maxlen = queue_maxlen
        self.ack_mode = ack_mode
        self.max_frame_bytes = max_frame_bytes
        self.idle_timeout_seconds = idle_timeout_seconds
        self._redis: aioredis.Redis | None = None
        self._retry_buffer: deque[str] = deque(maxlen=retry_buffer_maxlen)
        self._push_lock = asyncio.Lock()
        self._server: asyncio.Server | None = None

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Démarre le serveur et sert jusqu'à annulation de la tâche."""
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        bound = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        logger.info(
            "Listener TCP brut [%s] démarré sur %s (file Redis: %s, ack: %s, allowlist: %s)",
            self.analyzer_kind,
            bound,
            self.queue_key,
            self.ack_mode,
            sorted(self.allowed_ips) or "aucune (firewall)",
        )
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Arrêt propre : ferme le serveur puis la connexion Redis."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None
        logger.info("Listener TCP brut arrêté (%d trame(s) en tampon)", len(self._retry_buffer))

    # ── Gestion d'une connexion automate ─────────────────────────────────────

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peername = writer.get_extra_info("peername")
        source_ip = str(peername[0]) if peername else "unknown"
        source_port = int(peername[1]) if peername and len(peername) > 1 else 0

        if self.allowed_ips and source_ip not in self.allowed_ips:
            logger.warning(
                "Connexion refusée [%s] : IP %s hors allowlist %s",
                self.analyzer_kind,
                source_ip,
                sorted(self.allowed_ips),
            )
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return

        logger.info(
            "Connexion automate [%s] entrante depuis %s:%s",
            self.analyzer_kind,
            source_ip,
            source_port,
        )

        buffer = b""
        frame_count = 0
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        reader.read(65536), timeout=self.idle_timeout_seconds
                    )
                except TimeoutError:
                    logger.warning(
                        "Connexion automate %s:%s inactive depuis %.0fs, fermeture",
                        source_ip,
                        source_port,
                        self.idle_timeout_seconds,
                    )
                    break
                if not chunk:
                    break  # EOF : l'automate a fermé proprement.
                buffer += chunk

                frames, buffer = split_frames(buffer)
                for frame, hint in frames:
                    await self._store_frame(frame, hint, source_ip, source_port)
                    frame_count += 1
                    if not await self._acknowledge(writer, source_ip, source_port):
                        return
                if len(buffer) >= self.max_frame_bytes:
                    logger.warning(
                        "Trame sans délimiteur > %d octets depuis %s:%s — flush forcé",
                        self.max_frame_bytes,
                        source_ip,
                        source_port,
                    )
                    await self._store_frame(buffer, "overflow-flush", source_ip, source_port)
                    frame_count += 1
                    buffer = b""
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning(
                "Coupure brutale de la socket automate %s:%s : %s", source_ip, source_port, exc
            )
        finally:
            if buffer:
                # Trame incomplète à la déconnexion : archivée quand même,
                # marquée eof-flush — on ne perd jamais d'octets.
                await self._store_frame(buffer, "eof-flush", source_ip, source_port)
                frame_count += 1
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            logger.info(
                "Connexion automate %s:%s fermée (%d trame(s) archivée(s))",
                source_ip,
                source_port,
                frame_count,
            )

    async def _acknowledge(
        self, writer: asyncio.StreamWriter, source_ip: str, source_port: int
    ) -> bool:
        """Acquitte selon le mode configuré. Retourne False s'il faut fermer."""
        if self.ack_mode == "silent":
            return True
        if self.ack_mode == "close":
            logger.info(
                "Mode close : fermeture de la connexion %s:%s après réception",
                source_ip,
                source_port,
            )
            return False
        try:
            writer.write(ASCII_ACK)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("ACK impossible vers %s:%s : %s", source_ip, source_port, exc)
            return False
        return True

    # ── Archivage Redis ───────────────────────────────────────────────────────

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            logger.info("Client Redis initialisé pour la file %s", self.queue_key)
        return self._redis

    async def _reset_redis(self) -> None:
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None

    async def _store_frame(
        self, frame: bytes, delimiter_hint: str, source_ip: str, source_port: int
    ) -> None:
        payload = build_frame_payload(
            frame,
            analyzer_kind=self.analyzer_kind,
            listener_port=self.port,
            delimiter_hint=delimiter_hint,
            source_ip=source_ip,
            source_port=source_port,
        )
        async with self._push_lock:
            try:
                client = self._get_redis()
                # Rejouer d'abord les trames retenues pendant une panne Redis
                # (ordre préservé), puis pousser la nouvelle.
                while self._retry_buffer:
                    # cast : redis-py type ses commandes en ResponseT (sync | async).
                    await cast(
                        "Awaitable[int]", client.lpush(self.queue_key, self._retry_buffer[0])
                    )
                    self._retry_buffer.popleft()
                    logger.info(
                        "LPUSH %s ok (rejeu tampon, %d restante(s))",
                        self.queue_key,
                        len(self._retry_buffer),
                    )
                queue_len = await cast("Awaitable[int]", client.lpush(self.queue_key, payload))
                await cast("Awaitable[str]", client.ltrim(self.queue_key, 0, self.queue_maxlen - 1))
                logger.info(
                    "LPUSH %s ok [%s] : %d octets depuis %s:%s (%s), longueur file=%d",
                    self.queue_key,
                    self.analyzer_kind,
                    len(frame),
                    source_ip,
                    source_port,
                    delimiter_hint,
                    queue_len,
                )
            except (aioredis.RedisError, OSError) as exc:
                buf = self._retry_buffer
                if buf.maxlen is not None and len(buf) == buf.maxlen:
                    logger.error(
                        "Tampon mémoire plein (%d) : la trame la plus ancienne est PERDUE",
                        buf.maxlen,
                    )
                buf.append(payload)
                logger.error(
                    "LPUSH %s KO (%s) — trame de %s:%s mise en tampon mémoire (%d en attente)",
                    self.queue_key,
                    exc,
                    source_ip,
                    source_port,
                    len(buf),
                )
                await self._reset_redis()

"""Driver ASTM TCP/IP autonome pour automates de biologie -> RuggyLab OS.

Usage minimal:

    python scripts/astm_tcp_driver.py ^
      --listen-host 127.0.0.1 --listen-port 5002 ^
      --api-base http://127.0.0.1:8000/api/v1 ^
      --analyzer-key <CLE_MIDDLEWARE>

Le script écoute un port TCP local, reçoit des trames ASTM, extrait les
enregistrements O (Order/specimen) et R (Result), puis poste les résultats vers
RuggyLab OS via REST. Il ne dépend pas du backend FastAPI local: il peut tourner
sur un mini-PC placé entre l'automate et le serveur central.

Notes ASTM:
  - Le format ASTM E1381/E1394 varie selon les constructeurs. Ce driver couvre
    le squelette standard et documente les points à adapter.
  - Beaucoup d'automates encapsulent les records dans des trames:
      ENQ -> ACK
      STX + frame_number + payload + ETX/ETB + checksum + CR LF -> ACK
      EOT
  - Les records logiques sont séparés par CR et ressemblent à:
      O|1|SAMPLE-001||^^^NFS
      R|1|^^^HGB^1|4.8|g/dL|...
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger("ruggylab.astm_driver")

# Caractères de contrôle ASTM bas niveau.
ENQ = b"\x05"  # Enquiry: l'automate demande à parler.
ACK = b"\x06"  # Acknowledge: le middleware accepte / confirme une trame.
NAK = b"\x15"  # Negative ACK: trame refusée.
EOT = b"\x04"  # End of transmission.
STX = b"\x02"  # Start of text.
ETX = b"\x03"  # End of text, dernière trame du message.
ETB = b"\x17"  # End transmission block, trame intermédiaire.
CR = b"\x0d"
LF = b"\x0a"


@dataclass(frozen=True)
class ASTMResult:
    """Résultat unitaire extrait d'une ligne R ASTM."""

    sample_barcode: str
    test_code: str
    value: str
    unit: str | None = None
    raw_record: str | None = None


@dataclass(frozen=True)
class ASTMOrderBatch:
    """Résultats regroupés par échantillon pour un POST RuggyLab."""

    sample_barcode: str
    data_points: dict[str, Any]
    exam_code: str | None = None
    message_id: str | None = None
    raw_message_hash: str | None = None
    raw_results: list[ASTMResult] | None = None


def _first_component(value: str) -> str:
    """Retourne la première composante ASTM utile.

    Beaucoup de champs ASTM sont composites avec "^".
    Exemple:
      "SAMPLE-001^Rack42^Cup7" -> "SAMPLE-001"
      "^^^HGB^1"              -> "HGB" via _test_code_from_field()
    """
    return value.split("^")[0].strip()


def _test_code_from_field(universal_test_id: str) -> str | None:
    """Extrait un code analyte depuis le champ 3 d'un record R.

    En ASTM, R.3 est souvent "Universal Test ID". Selon les automates on voit:
      - "^^^HGB^1"          -> composante 4 = HGB
      - "HGB"               -> composante 1 = HGB
      - "1234^HGB^LN"       -> code local parfois en composante 2

    Stratégie conservatrice:
      1. découper sur "^";
      2. ignorer les composantes vides;
      3. préférer la composante 4 si elle existe, car c'est le cas courant ASTM;
      4. sinon prendre la dernière composante non vide.

    Pour un automate précis, adaptez cette fonction ou ajoutez un mapping:
      {"Leukocytes": "WBC", "Hemoglobin": "HGB", ...}
    """
    components = [part.strip() for part in universal_test_id.split("^")]
    if len(components) >= 4 and components[3]:
        return components[3]
    non_empty = [part for part in components if part]
    return non_empty[-1] if non_empty else None


def _clean_frame_payload(frame: bytes) -> str:
    """Retire l'enveloppe STX/ETX/checksum pour retrouver les records ASTM.

    Une trame physique ressemble souvent à:
      STX + "1H|...\\rO|...\\rR|...\\rL|1|N\\r" + ETX + "AB" + CR + LF

    Le premier caractère du payload est fréquemment le numéro de frame ("1").
    On le retire s'il précède immédiatement un record ASTM connu.
    """
    payload = frame
    if payload.startswith(STX):
        payload = payload[1:]
    end_positions = [pos for marker in (ETX, ETB) if (pos := payload.find(marker)) >= 0]
    if end_positions:
        payload = payload[: min(end_positions)]
    text = payload.decode("utf-8", errors="replace")
    if len(text) >= 2 and text[0].isdigit() and text[1] in {"H", "P", "O", "R", "C", "L"}:
        text = text[1:]
    return text


def astm_records_from_bytes(raw: bytes) -> list[str]:
    """Transforme des octets ASTM en records textuels H/P/O/R/L.

    Cette fonction accepte à la fois:
      - un message déjà désencapsulé en texte ASTM;
      - une suite de trames avec STX/ETX/checksum;
      - des caractères ENQ/ACK/EOT mêlés au flux.
    """
    chunks: list[str] = []
    remaining = raw

    while STX in remaining:
        before, after_stx = remaining.split(STX, 1)
        if before.strip(ENQ + ACK + NAK + EOT + CR + LF):
            chunks.append(before.decode("utf-8", errors="replace"))
        end_candidates = [pos for marker in (ETX, ETB) if (pos := after_stx.find(marker)) >= 0]
        if not end_candidates:
            chunks.append(after_stx.decode("utf-8", errors="replace"))
            remaining = b""
            break
        end = min(end_candidates)
        # Inclut ETX/ETB puis saute checksum(2) + CR/LF si présents.
        frame_end = min(len(after_stx), end + 1 + 2 + 2)
        chunks.append(_clean_frame_payload(STX + after_stx[:frame_end]))
        remaining = after_stx[frame_end:]

    if remaining.strip(ENQ + ACK + NAK + EOT + CR + LF):
        chunks.append(remaining.decode("utf-8", errors="replace"))

    text = "\r".join(chunks)
    text = text.replace("\x05", "").replace("\x06", "").replace("\x15", "").replace("\x04", "")
    text = text.replace("\n", "\r")
    return [line.strip() for line in text.split("\r") if line.strip()]


def parse_astm_message(raw: bytes | str) -> list[ASTMOrderBatch]:
    """Parse basique des records O/R ASTM.

    Records utilisés:
      - O = Order / Specimen. Le Sample ID est généralement en O.3
        (index Python 2 après split("|")). Certains automates placent l'ID en
        O.4: on essaie donc plusieurs champs.
      - R = Result. Le code test est généralement en R.3, la valeur en R.4,
        l'unité en R.5.

    La fonction retourne des lots par échantillon, prêts à être envoyés au REST:
      {"sample_barcode": "SAMPLE-001", "data_points": {"HGB": 4.8}}
    """
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    records = astm_records_from_bytes(raw_bytes)
    current_sample: str | None = None
    current_exam_code: str | None = None
    grouped: dict[str, list[ASTMResult]] = {}
    exam_code_by_sample: dict[str, str | None] = {}

    for record in records:
        fields = record.split("|")
        if not fields:
            continue
        record_type = fields[0].strip()

        if record_type == "O":
            # ASTM O record simplifié:
            #   O|seq|specimen_id|instrument_specimen_id|universal_test_id|...
            # Dans la vraie vie, specimen_id peut être:
            #   "BARCODE123"
            #   "BARCODE123^rack^position"
            #   vide, avec l'ID dans le champ suivant selon constructeur.
            candidate_fields = fields[2:4]
            current_sample = next(
                (
                    _first_component(candidate)
                    for candidate in candidate_fields
                    if candidate.strip()
                ),
                None,
            )
            current_exam_code = _test_code_from_field(fields[4]) if len(fields) > 4 else None
            if current_sample:
                grouped.setdefault(current_sample, [])
                exam_code_by_sample[current_sample] = current_exam_code
            else:
                LOGGER.warning("Record O sans Sample ID exploitable: %s", record)
            continue

        if record_type != "R":
            continue

        if not current_sample:
            LOGGER.warning("Record R ignore car aucun record O/Sample ID courant: %s", record)
            continue
        if len(fields) < 4:
            LOGGER.warning("Record R incomplet ignore: %s", record)
            continue

        test_code = _test_code_from_field(fields[2])
        value = fields[3].strip()
        unit = fields[4].strip() if len(fields) > 4 and fields[4].strip() else None
        if not test_code or not value:
            LOGGER.warning("Record R sans code test ou valeur ignore: %s", record)
            continue

        grouped.setdefault(current_sample, []).append(
            ASTMResult(
                sample_barcode=current_sample,
                test_code=test_code,
                value=value,
                unit=unit,
                raw_record=record,
            )
        )

    batches: list[ASTMOrderBatch] = []
    for sample_barcode, results in grouped.items():
        if not results:
            continue
        data_points = {
            result.test_code: {"value": _coerce_number(result.value), "unit": result.unit}
            if result.unit
            else _coerce_number(result.value)
            for result in results
        }
        batches.append(
            ASTMOrderBatch(
                sample_barcode=sample_barcode,
                data_points=data_points,
                exam_code=exam_code_by_sample.get(sample_barcode),
                raw_results=results,
            )
        )
    return batches


def _coerce_number(value: str) -> float | str:
    """Convertit une valeur numérique ASTM en float quand c'est possible."""
    normalized = value.strip().replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return value.strip()


def batch_idempotency_key(analyzer_id: str, batch: ASTMOrderBatch) -> str:
    """Clé stable middleware pour dédoublonner l'outbox locale et RuggyLab."""
    if batch.message_id:
        base = f"{analyzer_id}|{batch.message_id}|{batch.sample_barcode}"
    elif batch.raw_message_hash:
        base = f"{analyzer_id}|{batch.sample_barcode}|{batch.raw_message_hash}"
    else:
        base = json.dumps(
            {
                "analyzer_id": analyzer_id,
                "sample_barcode": batch.sample_barcode,
                "exam_code": batch.exam_code,
                "data_points": batch.data_points,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    return hashlib.sha256(base.encode()).hexdigest()


class SQLiteOutbox:
    """Outbox transactionnel local en SQLite WAL.

    Pourquoi SQLite WAL ici:
      - durable sur disque avant toute tentative réseau;
      - lecture/écriture plus robuste qu'un fichier JSONL si le PC est coupé;
      - statut explicite: pending, processing, sent, failed;
      - idempotence via clé unique, donc un même message ASTM rejoué ne duplique
        pas la file locale.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    sample_barcode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sent_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outbox_status_id
                ON outbox(status, id)
                """
            )

    async def enqueue(self, idempotency_key: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._enqueue_sync, idempotency_key, payload)

    def _enqueue_sync(self, idempotency_key: str, payload: dict[str, Any]) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outbox (idempotency_key, sample_barcode, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (idempotency_key, payload["sample_barcode"], payload_json),
            )

    async def claim_pending(self, limit: int = 20) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self._claim_pending_sync, limit)

    def _claim_pending_sync(self, limit: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT * FROM outbox
                WHERE status IN ('pending', 'failed')
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            row_ids = [row["id"] for row in rows]
            if row_ids:
                placeholders = ",".join("?" for _ in row_ids)
                conn.execute(
                    f"""
                    UPDATE outbox
                    SET status='processing', updated_at=CURRENT_TIMESTAMP
                    WHERE id IN ({placeholders})
                    """,
                    row_ids,
                )
            conn.commit()
            return rows

    async def mark_sent(self, row_id: int) -> None:
        await asyncio.to_thread(self._mark_sent_sync, row_id)

    def _mark_sent_sync(self, row_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status='sent', sent_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (row_id,),
            )

    async def mark_failed(self, row_id: int, error: str) -> None:
        await asyncio.to_thread(self._mark_failed_sync, row_id, error[:1000])

    def _mark_failed_sync(self, row_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status='failed',
                    attempts=attempts + 1,
                    last_error=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (error, row_id),
            )

    async def pending_count(self) -> int:
        return await asyncio.to_thread(self._pending_count_sync)

    def _pending_count_sync(self) -> int:
        with self._connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM outbox WHERE status IN ('pending', 'failed')"
                ).fetchone()[0]
            )


class RuggyLabRestClient:
    """Client REST central.

    Flux:
      POST /analyzer/results avec sample_barcode + data_points.

    Le serveur central résout le code-barres, applique l'idempotence et crée le
    résultat. C'est plus robuste que de faire un GET sample puis POST /results
    depuis le middleware.
    """

    def __init__(
        self,
        api_base: str,
        analyzer_key: str,
        analyzer_id: str,
        *,
        hmac_secret: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.analyzer_key = analyzer_key
        self.analyzer_id = analyzer_id
        self.hmac_secret = hmac_secret
        self.timeout_seconds = timeout_seconds

    def _headers(self, body: bytes) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Analyzer-Key": self.analyzer_key,
        }
        if self.hmac_secret:
            timestamp = str(int(time.time()))
            signed = f"{timestamp}.".encode() + body
            signature = hmac.new(
                self.hmac_secret.encode("utf-8"),
                signed,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Analyzer-Timestamp"] = timestamp
            headers["X-Analyzer-Signature"] = signature
        return headers

    def payload_from_batch(self, batch: ASTMOrderBatch) -> dict[str, Any]:
        return {
            "analyzer_id": self.analyzer_id,
            "message_id": batch.message_id,
            "sample_barcode": batch.sample_barcode,
            "exam_code": batch.exam_code,
            "data_points": batch.data_points,
            "raw_message_hash": batch.raw_message_hash,
        }

    async def post_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            response = await client.post(
                f"{self.api_base}/analyzer/results",
                headers=self._headers(body),
                content=body,
            )
            response.raise_for_status()
            return response.json()


class ASTMTCPDriver:
    """Serveur TCP asyncio recevant des transmissions ASTM."""

    def __init__(
        self,
        host: str,
        port: int,
        client: RuggyLabRestClient,
        outbox: SQLiteOutbox,
        *,
        dispatch_interval_seconds: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.client = client
        self.outbox = outbox
        self.dispatch_interval_seconds = dispatch_interval_seconds

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        LOGGER.info("Connexion automate ASTM: %s", peer)
        message_buffer = bytearray()
        frame_buffer = bytearray()

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break

                for byte in data:
                    b = bytes([byte])
                    if b == ENQ:
                        writer.write(ACK)
                        await writer.drain()
                        continue

                    if b == EOT:
                        await self._process_message(bytes(message_buffer))
                        message_buffer.clear()
                        frame_buffer.clear()
                        continue

                    frame_buffer.extend(b)
                    if b == LF and frame_buffer.startswith(STX):
                        message_buffer.extend(frame_buffer)
                        frame_buffer.clear()
                        writer.write(ACK)
                        await writer.drain()

                # Certains simulateurs envoient du texte ASTM brut sans EOT.
                if not frame_buffer.startswith(STX) and CR in frame_buffer:
                    message_buffer.extend(frame_buffer)
                    frame_buffer.clear()
        except Exception:
            LOGGER.exception("Erreur pendant la session ASTM avec %s", peer)
            writer.write(NAK)
            await writer.drain()
        finally:
            if message_buffer:
                await self._process_message(bytes(message_buffer))
            writer.close()
            await writer.wait_closed()
            LOGGER.info("Connexion automate fermee: %s", peer)

    async def _process_message(self, raw_message: bytes) -> None:
        raw_hash = hashlib.sha256(raw_message).hexdigest()
        batches = parse_astm_message(raw_message)
        if not batches:
            LOGGER.warning("Message ASTM sans résultat exploitable: %r", raw_message[:160])
            return
        for batch in batches:
            batch = ASTMOrderBatch(
                sample_barcode=batch.sample_barcode,
                data_points=batch.data_points,
                exam_code=batch.exam_code,
                message_id=batch.message_id,
                raw_message_hash=raw_hash,
                raw_results=batch.raw_results,
            )
            payload = self.client.payload_from_batch(batch)
            key = batch_idempotency_key(self.client.analyzer_id, batch)
            await self.outbox.enqueue(key, payload)
            LOGGER.info("Batch ASTM durablement inscrit en outbox: sample=%s", batch.sample_barcode)
        await self.dispatch_once()

    async def dispatch_once(self, limit: int = 20) -> int:
        rows = await self.outbox.claim_pending(limit=limit)
        sent = 0
        for row in rows:
            payload = json.loads(row["payload_json"])
            try:
                response = await self.client.post_payload(payload)
            except (httpx.HTTPError, OSError, TimeoutError) as exc:
                await self.outbox.mark_failed(row["id"], str(exc))
                LOGGER.error(
                    "Outbox ASTM non transmise: id=%s sample=%s error=%s",
                    row["id"],
                    row["sample_barcode"],
                    exc,
                )
                continue
            await self.outbox.mark_sent(row["id"])
            sent += 1
            LOGGER.info(
                "Outbox ASTM transmise: id=%s sample=%s response=%s",
                row["id"],
                row["sample_barcode"],
                response,
            )
        return sent

    async def dispatch_loop(self) -> None:
        while True:
            try:
                await self.dispatch_once()
            except Exception:
                LOGGER.exception("Erreur dispatcher outbox ASTM")
            await asyncio.sleep(self.dispatch_interval_seconds)

    async def serve_forever(self) -> None:
        server = await asyncio.start_server(self.handle_connection, self.host, self.port)
        sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        LOGGER.info("Driver ASTM en écoute sur %s", sockets)
        dispatcher = asyncio.create_task(self.dispatch_loop())
        async with server:
            try:
                await server.serve_forever()
            finally:
                dispatcher.cancel()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Driver ASTM TCP/IP -> RuggyLab OS REST")
    parser.add_argument("--listen-host", default=os.getenv("ASTM_LISTEN_HOST", "127.0.0.1"))
    parser.add_argument(
        "--listen-port",
        type=int,
        default=int(os.getenv("ASTM_LISTEN_PORT", "5002")),
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("RUGGYLAB_API_BASE", "http://127.0.0.1:8000/api/v1"),
        help="Base REST RuggyLab, ex: http://server:8000/api/v1",
    )
    parser.add_argument("--analyzer-id", default=os.getenv("ANALYZER_ID", "astm-middleware-01"))
    parser.add_argument("--analyzer-key", default=os.getenv("ANALYZER_API_KEY"))
    parser.add_argument("--hmac-secret", default=os.getenv("ANALYZER_HMAC_SECRET"))
    parser.add_argument(
        "--outbox-db",
        default=os.getenv("ASTM_OUTBOX_DB", "artifacts/astm_outbox.sqlite3"),
    )
    parser.add_argument(
        "--dispatch-interval-seconds",
        type=float,
        default=float(os.getenv("ASTM_DISPATCH_INTERVAL_SECONDS", "5")),
    )
    parser.add_argument("--log-level", default=os.getenv("ASTM_LOG_LEVEL", "INFO"))
    return parser


async def async_main() -> None:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    outbox = SQLiteOutbox(Path(args.outbox_db))
    if not args.analyzer_key:
        raise SystemExit("--analyzer-key ou ANALYZER_API_KEY est obligatoire")
    client = RuggyLabRestClient(
        args.api_base,
        args.analyzer_key,
        args.analyzer_id,
        hmac_secret=args.hmac_secret,
    )
    driver = ASTMTCPDriver(
        args.listen_host,
        args.listen_port,
        client,
        outbox,
        dispatch_interval_seconds=args.dispatch_interval_seconds,
    )
    await driver.serve_forever()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

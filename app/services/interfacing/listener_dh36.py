import asyncio
import datetime as dt
import logging

from app.db.session import SessionLocal
from app.services.interfacing.dh36_ingestion import ingest_dh36_message

logger = logging.getLogger(__name__)

MLLP_START_BLOCK = b"\x0b"
MLLP_END_BLOCK = b"\x1c\x0d"


class DH36Listener:
    def __init__(self, host: str = "0.0.0.0", port: int = 5001):
        self.host = host
        self.port = port
        self.equipment_name = "Dymind DH36"

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("DH36 connection received from %s", addr)
        buffer = b""
        while True:
            data = await reader.read(4096)
            if not data:
                break
            buffer += data

            while MLLP_END_BLOCK in buffer:
                full_message_raw, buffer = buffer.split(MLLP_END_BLOCK, 1)
                if MLLP_START_BLOCK not in full_message_raw:
                    continue
                _, hl7_payload = full_message_raw.split(MLLP_START_BLOCK, 1)
                hl7_string = hl7_payload.decode("utf-8", errors="ignore")
                asyncio.create_task(self.process_hl7_message(hl7_string))

                ack = (
                    f"MSH|^~\\&|RUGGYLAB|LAB|{self.equipment_name}|DYMIND|"
                    f"{dt.datetime.now().strftime('%Y%m%d%H%M%S')}||ACK|||2.3\rMSA|AA|1\r"
                ).encode("utf-8")
                writer.write(MLLP_START_BLOCK + ack + MLLP_END_BLOCK)
                await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def process_hl7_message(self, hl7_string: str) -> None:
        session = SessionLocal()
        try:
            outcome = ingest_dh36_message(session, raw_message=hl7_string)
            if outcome.duplicate:
                logger.info(
                    "Duplicate DH36 message ignored: %s",
                    outcome.message.message_control_id or outcome.message.raw_hash,
                )
            elif outcome.message.status == "rejected":
                logger.warning(
                    "DH36 message rejected: %s", outcome.message.rejection_reason
                )
        except Exception as exc:  # pragma: no cover - runtime I/O path
            logger.exception("Critical DH36 processing error: %s", exc)
            session.rollback()
        finally:
            session.close()

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        async with server:
            await server.serve_forever()

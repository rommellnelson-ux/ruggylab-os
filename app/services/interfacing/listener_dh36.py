import asyncio
import datetime as dt
import logging

from app.db.session import SessionLocal
from app.models import Equipment, Patient, Result, Sample
from app.services.interfacing.dymind_dh36 import DH36Parser
from app.services.validation.med_logic import validate_nfs_parameters

logger = logging.getLogger(__name__)

MLLP_START_BLOCK = b"\x0b"
MLLP_END_BLOCK = b"\x1c\x0d"


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


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
            parser = DH36Parser(hl7_string)
            info = parser.get_info()
            if not info["barcode"]:
                logger.warning("DH36 message without barcode")
                return

            sample = (
                session.query(Sample).filter(Sample.barcode == info["barcode"]).first()
            )
            if not sample:
                logger.warning(
                    "Unknown barcode received from DH36: %s", info["barcode"]
                )
                return

            patient = (
                session.query(Patient).filter(Patient.id == sample.patient_id).first()
            )
            if not patient:
                logger.warning("Sample %s is not linked to a patient", sample.barcode)
                return

            analysis_date = utcnow_naive()
            age_in_years = (
                analysis_date.year
                - patient.birth_date.year
                - (
                    (analysis_date.month, analysis_date.day)
                    < (patient.birth_date.month, patient.birth_date.day)
                )
            )
            results_raw = parser.parse_results()
            equipment = (
                session.query(Equipment)
                .filter(Equipment.name == self.equipment_name)
                .first()
            )
            validated_jsonb, is_panic = validate_nfs_parameters(
                results_raw,
                age_in_years,
                patient.sex,
                equipment.serial_number if equipment else None,
            )

            new_result = Result(
                sample_id=sample.id,
                equipment_id=equipment.id if equipment else None,
                analysis_date=analysis_date,
                data_points=validated_jsonb.model_dump(),
                is_critical=is_panic,
            )
            sample.status = "Termine"
            session.add(new_result)
            session.commit()
        except Exception as exc:  # pragma: no cover - runtime I/O path
            logger.exception("Critical DH36 processing error: %s", exc)
            session.rollback()
        finally:
            session.close()

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        async with server:
            await server.serve_forever()

import datetime as dt
import hashlib
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import DH36InboundMessage, Equipment, Patient, Result, Sample, User
from app.services.audit import log_audit_event
from app.services.interfacing.dymind_dh36 import DH36Parser
from app.services.inventory import InsufficientStockError, consume_reagents_for_result
from app.services.validation.med_logic import validate_nfs_parameters

DH36_EQUIPMENT_NAME = "Dymind DH36"


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class DH36IngestionOutcome:
    message: DH36InboundMessage
    duplicate: bool = False


def _raw_hash(raw_message: str) -> str:
    normalized = raw_message.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _patient_age(patient: Patient, analysis_date: dt.datetime) -> int:
    return (
        analysis_date.year
        - patient.birth_date.year
        - (
            (analysis_date.month, analysis_date.day)
            < (patient.birth_date.month, patient.birth_date.day)
        )
    )


def _reject(
    db: Session,
    message: DH36InboundMessage,
    *,
    reason: str,
    user: User | None,
) -> DH36IngestionOutcome:
    message.status = "rejected"
    message.rejection_reason = reason
    message.processed_at = utcnow_naive()
    log_audit_event(
        db,
        user=user,
        event_type="dh36.message.reject",
        entity_type="dh36_inbound_message",
        entity_id=str(message.id),
        payload={
            "sample_barcode": message.sample_barcode,
            "message_control_id": message.message_control_id,
            "reason": reason,
        },
    )
    db.commit()
    db.refresh(message)
    return DH36IngestionOutcome(message=message)


def ingest_dh36_message(
    db: Session,
    *,
    raw_message: str,
    user: User | None = None,
) -> DH36IngestionOutcome:
    message_hash = _raw_hash(raw_message)
    parser = DH36Parser(raw_message)
    info = parser.get_info()
    message_control_id = info.get("message_control_id")

    duplicate_query = db.query(DH36InboundMessage).filter(
        DH36InboundMessage.raw_hash == message_hash
    )
    if message_control_id:
        duplicate_query = db.query(DH36InboundMessage).filter(
            or_(
                DH36InboundMessage.raw_hash == message_hash,
                DH36InboundMessage.message_control_id == message_control_id,
            )
        )
    existing = duplicate_query.first()
    if existing:
        log_audit_event(
            db,
            user=user,
            event_type="dh36.message.duplicate",
            entity_type="dh36_inbound_message",
            entity_id=str(existing.id),
            payload={
                "sample_barcode": existing.sample_barcode,
                "message_control_id": existing.message_control_id,
                "result_id": existing.result_id,
            },
        )
        db.commit()
        db.refresh(existing)
        return DH36IngestionOutcome(message=existing, duplicate=True)

    message = DH36InboundMessage(
        raw_hash=message_hash,
        message_control_id=message_control_id,
        sample_barcode=info.get("barcode"),
        equipment_serial=info.get("equipment_serial"),
        status="received",
        raw_message=raw_message.strip(),
    )
    db.add(message)
    db.flush()

    if not message.sample_barcode:
        return _reject(
            db,
            message,
            reason="Message DH36 sans code-barres echantillon.",
            user=user,
        )

    sample = (
        db.query(Sample)
        .filter(Sample.barcode == message.sample_barcode)
        .with_for_update()
        .first()
    )
    if not sample:
        return _reject(
            db,
            message,
            reason=f"Code-barres inconnu: {message.sample_barcode}.",
            user=user,
        )

    patient = db.query(Patient).filter(Patient.id == sample.patient_id).first()
    if not patient:
        return _reject(
            db,
            message,
            reason=f"Echantillon {sample.barcode} sans patient valide.",
            user=user,
        )

    equipment_query = db.query(Equipment).filter(Equipment.name == DH36_EQUIPMENT_NAME)
    if message.equipment_serial:
        equipment_query = equipment_query.filter(
            or_(
                Equipment.serial_number == message.equipment_serial,
                Equipment.serial_number.is_(None),
            )
        )
    equipment = equipment_query.order_by(Equipment.serial_number.desc()).first()
    if not equipment:
        return _reject(
            db,
            message,
            reason="Equipement Dymind DH36 non enregistre.",
            user=user,
        )

    analysis_date = utcnow_naive()
    results_raw = parser.parse_results()
    if not results_raw:
        return _reject(
            db,
            message,
            reason="Message DH36 sans resultats OBX exploitables.",
            user=user,
        )

    validated_jsonb, is_panic = validate_nfs_parameters(
        results_raw,
        _patient_age(patient, analysis_date),
        patient.sex,
        equipment.serial_number,
    )
    result = Result(
        sample_id=sample.id,
        equipment_id=equipment.id,
        analysis_date=analysis_date,
        data_points=validated_jsonb.model_dump(),
        validator_id=user.id if user else None,
        is_validated=True,
        is_critical=is_panic,
    )
    sample.status = "Termine"
    db.add(result)
    db.flush()

    try:
        consume_reagents_for_result(
            db,
            result=result,
            user=user,
            source="dh36.ingest",
        )
    except InsufficientStockError as exc:
        db.delete(result)
        return _reject(
            db,
            message,
            reason=(
                "Stock reactif insuffisant: "
                + ", ".join(item.reagent_name for item in exc.items)
            ),
            user=user,
        )

    message.status = "processed"
    message.result_id = result.id
    message.processed_at = utcnow_naive()
    log_audit_event(
        db,
        user=user,
        event_type="dh36.message.process",
        entity_type="dh36_inbound_message",
        entity_id=str(message.id),
        payload={
            "sample_barcode": sample.barcode,
            "message_control_id": message.message_control_id,
            "result_id": result.id,
            "is_critical": is_panic,
        },
    )
    db.commit()
    db.refresh(message)
    return DH36IngestionOutcome(message=message)

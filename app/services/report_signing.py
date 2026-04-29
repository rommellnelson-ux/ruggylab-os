import datetime as dt
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ReportSignature, Result, User
from app.services.audit import log_audit_event
from app.services.pdf import build_simple_pdf


def utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _canonical_result_payload(result: Result) -> dict:
    sample = result.sample
    patient = sample.patient if sample else None
    equipment = result.equipment
    return {
        "result_id": result.id,
        "sample_id": result.sample_id,
        "sample_barcode": sample.barcode if sample else None,
        "patient_ipp": patient.ipp_unique_id if patient else None,
        "patient_name": (
            f"{patient.first_name} {patient.last_name}" if patient else None
        ),
        "patient_birth_date": (
            patient.birth_date.isoformat() if patient and patient.birth_date else None
        ),
        "patient_sex": patient.sex if patient else None,
        "equipment_id": result.equipment_id,
        "equipment_name": equipment.name if equipment else None,
        "equipment_serial": equipment.serial_number if equipment else None,
        "analysis_date": result.analysis_date.isoformat(),
        "data_points": result.data_points,
        "is_critical": result.is_critical,
        "is_validated": result.is_validated,
        "validator_id": result.validator_id,
    }


def report_hash(result: Result) -> str:
    payload = json.dumps(
        _canonical_result_payload(result),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signature_hash(
    *,
    result: Result,
    user: User,
    signature_meaning: str,
    report_digest: str,
    signed_at: dt.datetime,
) -> str:
    payload = "|".join(
        [
            str(result.id),
            str(user.id),
            user.username,
            report_digest,
            signed_at.isoformat(),
            signature_meaning,
        ]
    )
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_report_signature(
    db: Session,
    *,
    result: Result,
    user: User,
    signature_meaning: str,
) -> ReportSignature:
    signed_at = utcnow_naive()
    digest = report_hash(result)
    signature = ReportSignature(
        result_id=result.id,
        signed_by_user_id=user.id,
        report_hash=digest,
        signature_hash=signature_hash(
            result=result,
            user=user,
            signature_meaning=signature_meaning,
            report_digest=digest,
            signed_at=signed_at,
        ),
        signature_meaning=signature_meaning,
        signed_at=signed_at,
    )
    db.add(signature)
    db.flush()
    log_audit_event(
        db,
        user=user,
        event_type="report.sign",
        entity_type="result",
        entity_id=str(result.id),
        payload={
            "signature_id": signature.id,
            "report_hash": signature.report_hash,
            "signature_hash": signature.signature_hash,
            "signature_meaning": signature.signature_meaning,
        },
    )
    db.commit()
    db.refresh(signature)
    return signature


def build_result_report_pdf(result: Result, signature: ReportSignature | None) -> bytes:
    sample = result.sample
    patient = sample.patient if sample else None
    equipment = result.equipment
    lines = [
        "RuggyLab OS - Rapport biologique",
        f"Resultat: {result.id}",
        f"Echantillon: {sample.barcode if sample else result.sample_id}",
        f"Patient: {patient.first_name + ' ' + patient.last_name if patient else 'N/A'}",
        f"IPP: {patient.ipp_unique_id if patient else 'N/A'}",
        f"Sexe: {patient.sex if patient else 'N/A'}",
        f"Automate: {equipment.name if equipment else 'N/A'}",
        f"Numero serie: {equipment.serial_number if equipment else 'N/A'}",
        f"Date analyse: {result.analysis_date.isoformat()}",
        f"Valide: {'oui' if result.is_validated else 'non'}",
        f"Critique: {'oui' if result.is_critical else 'non'}",
        "",
        "Resultats:",
    ]
    for key, value in sorted(result.data_points.items()):
        if isinstance(value, dict):
            display = value.get("value", value)
            status = value.get("status", "")
            unit = value.get("unit", "")
            lines.append(f"- {key}: {display} {unit} {status}".strip())
        else:
            lines.append(f"- {key}: {value}")

    lines.extend(["", f"Empreinte rapport: {report_hash(result)}"])
    if signature:
        signer = signature.signed_by
        lines.extend(
            [
                "",
                "Signature electronique:",
                f"Officier: {signer.full_name or signer.username}",
                f"Date signature: {signature.signed_at.isoformat()}",
                f"Objet: {signature.signature_meaning}",
                f"Signature: {signature.signature_hash}",
            ]
        )
    else:
        lines.extend(["", "Signature electronique: non signee"])
    return build_simple_pdf(lines)

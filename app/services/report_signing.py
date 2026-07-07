import datetime as dt
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ReportDeliveryOutbox, ReportSignature, ReportSnapshot, Result, User
from app.services.audit import log_audit_event
from app.services.pdf import build_simple_pdf
from app.utils.datetime_utils import utcnow_naive


def _canonical_result_payload(result: Result) -> dict:
    sample = result.sample
    patient = sample.patient if sample else None
    equipment = result.equipment
    return {
        "result_id": result.id,
        "sample_id": result.sample_id,
        "sample_barcode": sample.barcode if sample else None,
        "patient_ipp": patient.ipp_unique_id if patient else None,
        "patient_name": (f"{patient.first_name} {patient.last_name}" if patient else None),
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


def _latest_snapshot(db: Session, result_id: int) -> ReportSnapshot | None:
    return (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.result_id == result_id, ReportSnapshot.revoked_at.is_(None))
        .order_by(ReportSnapshot.version_number.desc(), ReportSnapshot.id.desc())
        .first()
    )


def _next_snapshot_version(db: Session, result_id: int) -> int:
    latest = (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.result_id == result_id)
        .order_by(ReportSnapshot.version_number.desc())
        .first()
    )
    return 1 if latest is None else latest.version_number + 1


def _snapshot_token(snapshot: ReportSnapshot) -> str:
    payload = "|".join(
        [
            str(snapshot.id),
            str(snapshot.result_id),
            str(snapshot.version_number),
            snapshot.created_at.isoformat(),
        ]
    )
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"rs-{snapshot.id}-{digest}"


def report_snapshot_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verification_path_for_token(token: str) -> str:
    return f"/api/v1/reports/verify/{token}"


def _result_lines(result: Result) -> list[dict]:
    rows: list[dict] = []
    flags = result.flags or {}
    for code, raw in sorted((result.data_points or {}).items()):
        if isinstance(raw, dict):
            rows.append(
                {
                    "code": code,
                    "value": raw.get("value", raw),
                    "unit": raw.get("unit"),
                    "status": raw.get("status") or flags.get(code),
                    "reference_range": raw.get("reference_range") or raw.get("range"),
                }
            )
        else:
            rows.append(
                {
                    "code": code,
                    "value": raw,
                    "unit": None,
                    "status": flags.get(code),
                    "reference_range": None,
                }
            )
    return rows


def build_report_snapshot_payload(
    result: Result,
    *,
    audience: str,
    signature: ReportSignature | None,
) -> dict:
    sample = result.sample
    patient = sample.patient if sample else None
    equipment = result.equipment
    return {
        "schema_version": "1.0",
        "audience": audience,
        "result": {
            "id": result.id,
            "exam_code": result.exam_code,
            "analysis_date": result.analysis_date.isoformat(),
            "is_validated": result.is_validated,
            "is_critical": result.is_critical,
            "critical_ack_at": result.critical_ack_at.isoformat()
            if result.critical_ack_at
            else None,
            "bio_validated_at": result.bio_validated_at.isoformat()
            if result.bio_validated_at
            else None,
            "bio_review_status": result.bio_review_status,
            "bio_reviewed_at": result.bio_reviewed_at.isoformat()
            if result.bio_reviewed_at
            else None,
            "bio_reviewed_by_id": result.bio_reviewed_by_id,
            "rows": _result_lines(result),
            "bioref_status": result.bioref_status,
            "bioref_comment": result.bioref_comment,
            "bioref_reference_range": result.bioref_reference_range,
            "bioref_source": result.bioref_source,
            "amendment_reason": result.amendment_reason,
        },
        "sample": {
            "id": sample.id if sample else None,
            "barcode": sample.barcode if sample else None,
            "collection_date": sample.collection_date.isoformat() if sample else None,
            "received_date": sample.received_date.isoformat()
            if sample and sample.received_date
            else None,
            "status": sample.status if sample else None,
        },
        "patient": {
            "id": patient.id if patient else None,
            "ipp": patient.ipp_unique_id if patient else None,
            "name": f"{patient.first_name} {patient.last_name}" if patient else None,
            "birth_date": patient.birth_date.isoformat() if patient else None,
            "sex": patient.sex if patient else None,
            "unit": patient.unit if patient else None,
        },
        "equipment": {
            "id": equipment.id if equipment else None,
            "name": equipment.name if equipment else None,
            "serial_number": equipment.serial_number if equipment else None,
        },
        "signature": {
            "id": signature.id if signature else None,
            "signed_by": (
                signature.signed_by.full_name or signature.signed_by.username if signature else None
            ),
            "signed_at": signature.signed_at.isoformat() if signature else None,
            "signature_hash": signature.signature_hash if signature else None,
            "meaning": signature.signature_meaning if signature else None,
            "revoked_at": signature.revoked_at.isoformat()
            if signature and signature.revoked_at
            else None,
        },
    }


def build_snapshot_pdf_lines(snapshot: ReportSnapshot, verification_url: str) -> list[str]:
    payload = snapshot.content_snapshot or {}
    result = payload.get("result", {})
    patient = payload.get("patient", {})
    sample = payload.get("sample", {})
    equipment = payload.get("equipment", {})
    signature = payload.get("signature", {})
    lines = [
        "RuggyLab OS - Compte-rendu versionne",
        "Document medical confidentiel",
        f"Compte-rendu: resultat #{result.get('id')} / version {snapshot.version_number}",
        f"Statut du document: {snapshot.status}",
        "Mention validation: "
        + (
            "resultat valide selon la procedure en vigueur"
            if result.get("is_validated")
            else "resultat provisoire"
        ),
        f"Patient: {patient.get('name') or 'N/A'}",
        f"IPP: {patient.get('ipp') or 'N/A'}",
        f"Date de naissance: {patient.get('birth_date') or 'N/A'}",
        f"Sexe: {patient.get('sex') or 'N/A'}",
        f"Unite: {patient.get('unit') or 'N/A'}",
        f"Echantillon: {sample.get('barcode') or sample.get('id') or 'N/A'}",
        f"Prelevement: {sample.get('collection_date') or 'N/A'}",
        f"Reception: {sample.get('received_date') or 'N/A'}",
        f"Automate: {equipment.get('name') or 'N/A'}",
        f"Numero serie: {equipment.get('serial_number') or 'N/A'}",
        f"Date analyse: {result.get('analysis_date') or 'N/A'}",
        f"Validation operationnelle: {result.get('bio_validated_at') or 'non renseignee'}",
        "Revue biologique differee: "
        + (
            f"effectuee le {result.get('bio_reviewed_at')}"
            if result.get("bio_review_status") == "reviewed"
            else "en attente - sans effet bloquant sur ce resultat"
        ),
        f"Valeur critique: {'oui' if result.get('is_critical') else 'non'}",
        "Prise en charge critique: "
        + (
            result.get("critical_ack_at")
            if result.get("is_critical") and result.get("critical_ack_at")
            else "requise"
            if result.get("is_critical")
            else "non applicable"
        ),
        "",
        "Resultats (unite, statut et intervalle de reference si disponibles):",
    ]
    for row in result.get("rows", []):
        unit = f" {row.get('unit')}" if row.get("unit") else ""
        status = f" | statut: {row.get('status')}" if row.get("status") else ""
        reference = (
            f" | intervalle de reference: {row.get('reference_range')}"
            if row.get("reference_range")
            else ""
        )
        lines.append(f"- {row.get('code')}: {row.get('value')}{unit}{status}{reference}")

    if result.get("bioref_status") or result.get("bioref_comment"):
        lines += [
            "",
            "Interpretation biologique aidee:",
            f"Statut: {result.get('bioref_status') or 'non renseigne'}",
            f"Intervalle de reference: {result.get('bioref_reference_range') or 'non disponible'}",
            f"Commentaire: {result.get('bioref_comment') or 'non renseigne'}",
        ]
    if signature.get("signature_hash") and not signature.get("revoked_at"):
        lines += [
            "",
            "Signature electronique:",
            f"Signataire: {signature.get('signed_by') or 'N/A'}",
            f"Date signature: {signature.get('signed_at') or 'N/A'}",
            f"Objet: {signature.get('meaning') or 'N/A'}",
            f"Signature: {signature.get('signature_hash')}",
        ]
    else:
        lines += ["", "Signature electronique: non signee"]

    lines += [
        "",
        "Note patient: ce compte-rendu doit etre interprete avec le contexte clinique.",
        f"Verification: {verification_url}",
        "Empreinte PDF: disponible sur la page de verification.",
    ]
    if snapshot.status == "corrected":
        lines.append("Mention: compte-rendu corrige - une version plus recente existe.")
    if snapshot.revoked_at:
        lines.append("Mention: compte-rendu revoque - ne pas utiliser.")
    return lines


def build_snapshot_pdf(snapshot: ReportSnapshot) -> bytes:
    token = _snapshot_token(snapshot)
    return build_simple_pdf(build_snapshot_pdf_lines(snapshot, verification_path_for_token(token)))


def release_result_report(
    db: Session,
    *,
    result: Result,
    user: User,
    audience: str = "clinician",
    signature: ReportSignature | None = None,
    delivery_channels: list[str] | None = None,
) -> ReportSnapshot:
    previous = _latest_snapshot(db, result.id)
    if previous and previous.status in {"final", "provisional"}:
        previous.status = "corrected"

    payload = build_report_snapshot_payload(result, audience=audience, signature=signature)
    snapshot = ReportSnapshot(
        result_id=result.id,
        version_number=_next_snapshot_version(db, result.id),
        status="final" if result.is_validated else "provisional",
        audience=audience,
        schema_version="1.0",
        content_snapshot=payload,
        pdf_sha256="0" * 64,
        verification_token_hash="0" * 64,
        verification_path="pending",
        supersedes_snapshot_id=previous.id if previous else None,
        created_by_user_id=user.id,
    )
    db.add(snapshot)
    db.flush()
    token = _snapshot_token(snapshot)
    snapshot.verification_token_hash = report_snapshot_token_hash(token)
    snapshot.verification_path = verification_path_for_token(token)
    provisional_pdf = build_snapshot_pdf(snapshot)
    snapshot.pdf_sha256 = hashlib.sha256(provisional_pdf).hexdigest()

    channels = delivery_channels or ["internal"]
    for channel in channels:
        event = ReportDeliveryOutbox(
            report_snapshot_id=snapshot.id,
            event_type="report.released",
            channel=channel,
            status="pending",
            idempotency_key=f"report:{snapshot.id}:released:{channel}",
            payload={
                "snapshot_id": snapshot.id,
                "result_id": result.id,
                "version_number": snapshot.version_number,
                "verification_path": snapshot.verification_path,
            },
            next_attempt_at=utcnow_naive(),
        )
        db.add(event)
    log_audit_event(
        db,
        user=user,
        event_type="report.release",
        entity_type="report_snapshot",
        entity_id=str(snapshot.id),
        payload={
            "result_id": result.id,
            "version_number": snapshot.version_number,
            "status": snapshot.status,
            "audience": audience,
        },
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def reissue_report_signature(
    db: Session,
    *,
    signature: ReportSignature,
    result: Result,
    user: User,
    signature_meaning: str,
) -> ReportSignature:
    signed_at = utcnow_naive()
    digest = report_hash(result)
    signature.signed_by_user_id = user.id
    signature.report_hash = digest
    signature.signature_hash = signature_hash(
        result=result,
        user=user,
        signature_meaning=signature_meaning,
        report_digest=digest,
        signed_at=signed_at,
    )
    signature.signature_meaning = signature_meaning
    signature.signed_at = signed_at
    signature.revoked_at = None
    signature.revocation_reason = None
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
            "reissued": True,
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
        "RuggyLab OS - Compte-rendu de resultat",
        "Document medical confidentiel",
        f"Compte-rendu: resultat #{result.id}",
        f"Echantillon: {sample.barcode if sample else result.sample_id}",
        f"Patient: {patient.first_name + ' ' + patient.last_name if patient else 'N/A'}",
        f"IPP: {patient.ipp_unique_id if patient else 'N/A'}",
        f"Sexe: {patient.sex if patient else 'N/A'}",
        f"Date de naissance: {patient.birth_date.isoformat() if patient and patient.birth_date else 'N/A'}",
        f"Automate: {equipment.name if equipment else 'N/A'}",
        f"Numero serie: {equipment.serial_number if equipment else 'N/A'}",
        f"Date analyse: {result.analysis_date.isoformat()}",
        f"Statut validation: {'valide' if result.is_validated else 'non valide'}",
        f"Valeur critique: {'oui' if result.is_critical else 'non'}",
        "Prise en charge critique: "
        + (
            result.critical_ack_at.isoformat()
            if result.is_critical and result.critical_ack_at
            else "requise"
            if result.is_critical
            else "non applicable"
        ),
        "",
        "Resultats (unite, statut et intervalle de reference si disponibles):",
    ]
    for key, value in sorted(result.data_points.items()):
        if isinstance(value, dict):
            display = value.get("value", value)
            status = value.get("status", "")
            unit = value.get("unit", "")
            reference = value.get("reference_range") or value.get("range") or ""
            suffix = f" | intervalle de reference: {reference}" if reference else ""
            lines.append(f"- {key}: {display} {unit} {status}{suffix}".strip())
        else:
            flag = (result.flags or {}).get(key, "")
            suffix = f" | statut: {flag}" if flag else ""
            lines.append(f"- {key}: {value}{suffix}")

    if result.bioref_status or result.bioref_comment or result.bioref_reference_range:
        lines.extend(
            [
                "",
                "Interpretation biologique aidee:",
                f"Statut: {result.bioref_status or 'non renseigne'}",
                f"Intervalle de reference: {result.bioref_reference_range or 'non disponible'}",
                f"Commentaire: {result.bioref_comment or 'non renseigne'}",
            ]
        )

    lines.extend(
        [
            "",
            "Note patient: ce compte-rendu doit etre interprete avec le contexte clinique.",
            f"Empreinte rapport: {report_hash(result)}",
        ]
    )
    if signature and signature.revoked_at is None:
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
    elif signature and signature.revoked_at is not None:
        lines.extend(
            [
                "",
                "Signature electronique: revoquee",
                f"Date revocation: {signature.revoked_at.isoformat()}",
                f"Motif: {signature.revocation_reason or 'non renseigne'}",
                "Ce PDF ne doit pas etre considere comme un compte-rendu signe valide.",
            ]
        )
    else:
        lines.extend(["", "Signature electronique: non signee"])
    return build_simple_pdf(lines)

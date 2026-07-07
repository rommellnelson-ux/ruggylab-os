"""Interopérabilité contrôlée avec CSA PLATEAU via les RPC Supabase dédiées."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    CsaExamMapping,
    CsaPatientLink,
    CsaPrescriptionLink,
    ExamOrder,
    ExamOrderItem,
    Patient,
    Result,
)
from app.schemas.csa_plateau import CSAContractTestRequest, CSAIntegrationStatus


class CSAPlateauAdapter(Protocol):
    def status(self) -> CSAIntegrationStatus: ...
    def contract_key(self, payload: CSAContractTestRequest) -> str: ...
    def pull_prescriptions(self, changed_since: dt.datetime | None, limit: int) -> list[dict]: ...
    def push_event(self, event_kind: str, source_item_id: str, payload: dict) -> str: ...


def contract_idempotency_key(payload: CSAContractTestRequest) -> str:
    if payload.idempotency_key:
        return payload.idempotency_key
    canonical = json.dumps(
        payload.model_dump(mode="json", exclude={"idempotency_key"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return f"csa-preview-{hashlib.sha256(canonical).hexdigest()[:40]}"


def _configured() -> bool:
    return all(
        (
            settings.CSA_PLATEAU_BASE_URL,
            settings.CSA_PLATEAU_ANON_KEY,
            settings.CSA_PLATEAU_TECHNICAL_EMAIL,
            settings.CSA_PLATEAU_TECHNICAL_PASSWORD,
        )
    )


class DisabledCSAPlateauAdapter:
    def status(self) -> CSAIntegrationStatus:
        return CSAIntegrationStatus(
            enabled=settings.CSA_PLATEAU_ENABLED,
            patient_exchange_enabled=settings.CSA_PLATEAU_PATIENT_EXCHANGE_ENABLED,
            base_url_configured=bool(settings.CSA_PLATEAU_BASE_URL),
            reason="Connecteur désactivé ou configuration STAGING incomplète.",
        )

    def contract_key(self, payload: CSAContractTestRequest) -> str:
        return contract_idempotency_key(payload)

    def pull_prescriptions(self, changed_since: dt.datetime | None, limit: int) -> list[dict]:
        del changed_since, limit
        raise RuntimeError("Connecteur CSA PLATEAU désactivé.")

    def push_event(self, event_kind: str, source_item_id: str, payload: dict) -> str:
        del event_kind, source_item_id, payload
        raise RuntimeError("Connecteur CSA PLATEAU désactivé.")


class SupabaseCSAPlateauAdapter(DisabledCSAPlateauAdapter):
    def _headers(self) -> dict[str, str]:
        base_url = str(settings.CSA_PLATEAU_BASE_URL).rstrip("/")
        if not settings.TESTING and not base_url.startswith("https://"):
            raise RuntimeError("CSA PLATEAU exige une URL HTTPS.")
        auth = httpx.post(
            f"{base_url}/auth/v1/token?grant_type=password",
            headers={"apikey": str(settings.CSA_PLATEAU_ANON_KEY)},
            json={
                "email": settings.CSA_PLATEAU_TECHNICAL_EMAIL,
                "password": settings.CSA_PLATEAU_TECHNICAL_PASSWORD,
            },
            timeout=settings.CSA_PLATEAU_TIMEOUT_SECONDS,
        )
        auth.raise_for_status()
        token = auth.json()["access_token"]
        return {
            "apikey": str(settings.CSA_PLATEAU_ANON_KEY),
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def status(self) -> CSAIntegrationStatus:
        return CSAIntegrationStatus(
            enabled=True,
            patient_exchange_enabled=True,
            base_url_configured=True,
            reason="Connecteur Supabase STAGING configuré; transport disponible.",
            transport_available=True,
            operational=True,
        )

    def pull_prescriptions(self, changed_since: dt.datetime | None, limit: int) -> list[dict]:
        base_url = str(settings.CSA_PLATEAU_BASE_URL).rstrip("/")
        response = httpx.post(
            f"{base_url}/rest/v1/rpc/csa_ruggylab_pull_prescriptions",
            headers=self._headers(),
            json={
                "changed_since": (changed_since or dt.datetime(1970, 1, 1)).isoformat(),
                "max_rows": min(max(limit, 1), 500),
            },
            timeout=settings.CSA_PLATEAU_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    def push_event(self, event_kind: str, source_item_id: str, payload: dict) -> str:
        base_url = str(settings.CSA_PLATEAU_BASE_URL).rstrip("/")
        response = httpx.post(
            f"{base_url}/rest/v1/rpc/csa_ruggylab_push_event",
            headers=self._headers(),
            json={
                "event_kind": event_kind,
                "source_item_id": source_item_id,
                "event_payload": payload,
            },
            timeout=settings.CSA_PLATEAU_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return str(response.json())


def get_csa_plateau_adapter() -> CSAPlateauAdapter:
    if (
        settings.CSA_PLATEAU_ENABLED
        and settings.CSA_PLATEAU_PATIENT_EXCHANGE_ENABLED
        and _configured()
    ):
        return SupabaseCSAPlateauAdapter()
    return DisabledCSAPlateauAdapter()


def _payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_ipp(db: Session) -> str:
    for _ in range(10):
        ipp = f"RGL-{dt.date.today():%y%m}-{secrets.token_hex(5).upper()}"
        if not db.query(Patient.id).filter(Patient.ipp_unique_id == ipp).first():
            return ipp
    raise ValueError("Impossible de générer un IPP RuggyLab unique.")


def import_prescription_event(db: Session, event: dict, *, created_by_id: int) -> tuple[str, int]:
    payload = event.get("payload") or {}
    external_prescription_id = str(payload.get("prescription_id") or event.get("item_id") or "")
    external_patient_id = str(payload.get("patient_id") or "")
    if not external_prescription_id or not external_patient_id:
        raise ValueError("Prescription CSA sans identifiant de prescription ou patient.")
    existing = (
        db.query(CsaPrescriptionLink)
        .filter(CsaPrescriptionLink.external_prescription_id == external_prescription_id)
        .first()
    )
    if existing:
        return "replayed", existing.exam_order_id

    link = (
        db.query(CsaPatientLink)
        .filter(
            CsaPatientLink.source_system == "CSA_PLATEAU",
            CsaPatientLink.external_patient_id == external_patient_id,
        )
        .first()
    )
    if link is None:
        birth_raw = str(payload.get("date_naissance") or "").strip()
        name = str(payload.get("patient_nom") or "").strip()
        if not birth_raw or not name:
            raise ValueError("Identité CSA incomplète : nom et date de naissance requis.")
        try:
            birth_date = dt.date.fromisoformat(birth_raw)
        except ValueError as exc:
            raise ValueError("Date de naissance CSA invalide.") from exc
        sex = str(payload.get("sexe") or "U").upper()
        patient = Patient(
            ipp_unique_id=_new_ipp(db),
            first_name="Non renseigné",
            last_name=name,
            birth_date=birth_date,
            sex=sex if sex in {"M", "F"} else None,
            unit="CSA PLATEAU",
        )
        db.add(patient)
        db.flush()
        link = CsaPatientLink(
            external_patient_id=external_patient_id,
            external_dossier_no=payload.get("dossier_no"),
            patient_id=patient.id,
        )
        db.add(link)
        db.flush()

    items: list[ExamOrderItem] = []
    missing = []
    for exam in payload.get("examens") or []:
        csa_code = str(exam.get("code") or "").upper()
        mappings = (
            db.query(CsaExamMapping)
            .filter(CsaExamMapping.csa_exam_code == csa_code, CsaExamMapping.active.is_(True))
            .all()
        )
        if not mappings:
            missing.append(csa_code or "?")
            continue
        for mapping in mappings:
            if not any(item.exam_code == mapping.ruggylab_exam_code for item in items):
                items.append(
                    ExamOrderItem(
                        exam_code=mapping.ruggylab_exam_code,
                        exam_label=exam.get("nom"),
                    )
                )
    if missing:
        raise ValueError(f"Mapping d'examen CSA manquant : {', '.join(missing)}.")
    if not items:
        raise ValueError("Prescription CSA sans examen exploitable.")
    order = ExamOrder(
        patient_id=link.patient_id,
        prescriber=f"{payload.get('prescripteur_nom') or 'CSA'} ({payload.get('prescripteur_role') or 'non précisé'})",
        requesting_service="CSA PLATEAU",
        clinical_info=payload.get("motif"),
        priority="urgent" if payload.get("priorite") == "urgent" else "routine",
        status="prescribed",
        created_by_id=created_by_id,
        items=items,
    )
    db.add(order)
    db.flush()
    db.add(
        CsaPrescriptionLink(
            external_prescription_id=external_prescription_id,
            external_event_key=str(event.get("event_key") or external_prescription_id),
            exam_order_id=order.id,
            payload_sha256=_payload_hash(payload),
        )
    )
    return "imported", order.id


def result_payload_for_csa(db: Session, result: Result) -> tuple[str, dict]:
    order_link = (
        db.query(CsaPrescriptionLink)
        .join(ExamOrder, ExamOrder.id == CsaPrescriptionLink.exam_order_id)
        .filter(ExamOrder.sample_id == result.sample_id)
        .first()
    )
    if order_link is None:
        raise ValueError("Ce résultat n'est pas lié à une prescription CSA.")
    patient_link = (
        db.query(CsaPatientLink)
        .join(ExamOrder, ExamOrder.patient_id == CsaPatientLink.patient_id)
        .filter(ExamOrder.id == order_link.exam_order_id)
        .first()
    )
    if patient_link is None:
        raise ValueError("Correspondance patient CSA introuvable.")
    payload = {
        "prescription_id": order_link.external_prescription_id,
        "patient_id": patient_link.external_patient_id,
        "dossier_no": patient_link.external_dossier_no,
        "ruggylab_result_id": result.id,
        "exam_code": result.exam_code,
        "valeurs": result.data_points,
        "statut": "valide" if result.is_validated else "provisoire",
        "critique": result.is_critical,
        "analyse_le": result.analysis_date.isoformat(),
    }
    return f"{order_link.external_prescription_id}:{result.id}", payload

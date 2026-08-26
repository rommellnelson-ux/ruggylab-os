"""Flux entrant CSA → RuggyLab : prescriptions ``labo_prescriptions`` → ordres.

``apply_prescription`` est **pur** (session + payload, aucun réseau) : c'est la
logique de mapping testable. ``poll_once`` l'orchestre autour du client CSA
(watermark, accusés de réception).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import CsaSyncState, ExamOrder, ExamOrderItem, Patient
from app.services.exam_catalog import exam_catalog_entry
from app.utils.datetime_utils import utcnow_naive

from . import exam_map

logger = logging.getLogger(__name__)

# Sentinelle quand la date de naissance CSA est absente (birth_date NOT NULL côté
# RuggyLab). Le patient est marqué birth_date_estimee=True, à compléter plus tard.
_SENTINEL_DOB = dt.date(1900, 1, 1)
_PRIORITIES = {"routine", "urgent", "stat"}


def _parse_dob(raw: Any) -> tuple[dt.date, bool]:
    """(date, estimee). Sentinelle + estimee=True si absente/invalide."""
    if raw:
        try:
            return dt.date.fromisoformat(str(raw)[:10]), False
        except ValueError:
            pass
    return _SENTINEL_DOB, True


def _split_name(full: str) -> tuple[str, str]:
    """« NOM Prénoms » (convention CSA) → (last_name, first_name)."""
    parts = (full or "").split()
    if not parts:
        return "INCONNU", "—"
    if len(parts) == 1:
        return parts[0], "—"
    return parts[0], " ".join(parts[1:])


def _upsert_patient(db: Session, payload: dict) -> Patient:
    dossier = (payload.get("dossier_no") or payload.get("patient_id") or "").strip()
    ipp = f"CSA-{dossier}" if dossier else f"CSA-UNK-{payload.get('prescription_id')}"
    patient = db.query(Patient).filter(Patient.ipp_unique_id == ipp).one_or_none()
    last_name, first_name = _split_name(payload.get("patient_nom", ""))
    dob, estimee = _parse_dob(payload.get("date_naissance"))
    sexe = str(payload.get("sexe") or "").strip().upper()[:1]
    sex = sexe if sexe in ("M", "F") else None
    if patient is None:
        patient = Patient(
            ipp_unique_id=ipp,
            first_name=first_name,
            last_name=last_name,
            birth_date=dob,
            birth_date_estimee=estimee,
            sex=sex,
        )
        db.add(patient)
        db.flush()  # attribue patient.id
    else:
        # Complète une DDN réelle si on n'avait qu'une sentinelle ; ne dégrade jamais.
        if patient.birth_date_estimee and not estimee:
            patient.birth_date = dob
            patient.birth_date_estimee = False
        if sex and not patient.sex:
            patient.sex = sex
    return patient


def _order_items(payload: dict) -> list[ExamOrderItem]:
    items: list[ExamOrderItem] = []
    for exam in payload.get("examens") or []:
        csa_code = (exam.get("code") or "").strip()
        csa_label = exam.get("nom") or csa_code
        mapped = exam_map.map_exam(csa_code)
        if mapped:
            for rl_code in mapped:
                entry = exam_catalog_entry(rl_code)
                items.append(
                    ExamOrderItem(
                        exam_code=rl_code,
                        exam_label=(entry or {}).get("label") or csa_label,
                        status="pending",
                    )
                )
        else:
            # Jamais perdu : item conservé avec le code CSA, signalé « unmapped ».
            items.append(
                ExamOrderItem(
                    exam_code=f"CSA:{csa_code}" if csa_code else "CSA:?",
                    exam_label=csa_label,
                    status="unmapped",
                )
            )
    return items


def apply_prescription(db: Session, payload: dict) -> ExamOrder:
    """Transforme une prescription CSA en ExamOrder RuggyLab (idempotent).

    Ré-appliquer la même prescription (même ``prescription_id``) renvoie l'ordre
    existant sans rien recréer.
    """
    presc_id = str(payload.get("prescription_id") or "").strip()
    if not presc_id:
        raise ValueError("prescription sans prescription_id")

    existing = db.query(ExamOrder).filter(ExamOrder.csa_prescription_id == presc_id).one_or_none()
    if existing is not None:
        return existing

    patient = _upsert_patient(db, payload)
    priority = str(payload.get("priorite") or "routine").strip().lower()
    if priority not in _PRIORITIES:
        priority = "routine"

    order = ExamOrder(
        patient_id=patient.id,
        prescriber=payload.get("prescripteur_nom"),
        requesting_service=payload.get("origine") or "CSA Plateau",
        clinical_info=payload.get("motif"),
        priority=priority,
        status="prescribed",
        csa_prescription_id=presc_id,
        items=_order_items(payload),
    )
    db.add(order)
    db.flush()
    logger.info(
        "CSA prescription %s -> ExamOrder %s (%d examens)",
        presc_id,
        order.id,
        len(order.items),
    )
    return order


def poll_once(db: Session, client) -> dict:
    """Un cycle de synchro entrant : pull → apply → accusé → avance le watermark.

    ``client`` expose ``pull_prescriptions(changed_since, max_rows)`` et
    ``push_event(kind, source_item_id, payload)``. Renvoie un résumé.
    """
    state = db.get(CsaSyncState, 1) or CsaSyncState(id=1)
    if state.id is None or db.get(CsaSyncState, 1) is None:
        db.add(state)
    since = state.last_pulled_at or "1970-01-01T00:00:00+00:00"

    rows = client.pull_prescriptions(changed_since=since, max_rows=100)
    processed, watermark = 0, state.last_pulled_at
    for row in rows:
        payload = row.get("payload") or {}
        order = apply_prescription(db, payload)
        presc_id = str(payload.get("prescription_id"))
        client.push_event(
            "labo_receipts",
            presc_id,
            # prescription_id DANS le payload : côté CSA, la synchro ne conserve que
            # le payload (l'item_id est perdu), donc le lien doit y figurer.
            {"statut": "recu", "prescription_id": presc_id, "lab_order_id": order.id},
        )
        processed += 1
        watermark = row.get("updated_at") or watermark

    state.last_pulled_at = watermark
    state.last_run_at = utcnow_naive()
    state.last_error = None
    state.processed_count = (state.processed_count or 0) + processed
    db.commit()
    return {"processed": processed, "watermark": watermark}


def run_sync_cycle() -> dict:
    """Ouvre une session + un client CSA et exécute un cycle. Ferme tout ensuite."""
    from app.db.session import SessionLocal

    from .client import build_client_from_settings

    client = build_client_from_settings()
    db = SessionLocal()
    try:
        return poll_once(db, client)
    finally:
        db.close()
        client.close()


async def periodic_csa_sync(interval_seconds: int) -> None:
    """Boucle du worker (process scheduler). Un échec de cycle ne tue pas la boucle.

    Chaque tick fait les DEUX sens : entrant (prescriptions→ordres) puis sortant
    (résultats validés→CSA). Les deux ont une gestion d'erreur indépendante :
    l'échec de l'un n'empêche pas l'autre ni les tours suivants.
    """
    import asyncio

    from .outbound import run_outbound_cycle

    logger.info("Worker de synchro CSA démarré (intervalle %ss)", interval_seconds)
    while True:
        try:
            summary = await asyncio.to_thread(run_sync_cycle)
            if summary.get("processed"):
                logger.info(
                    "Synchro CSA entrante : %d prescription(s) intégrée(s)", summary["processed"]
                )
        except Exception:  # noqa: BLE001 — resilience : on réessaie au tour suivant
            logger.exception("Cycle entrant CSA échoué (nouvelle tentative au prochain tour)")
        try:
            out = await asyncio.to_thread(run_outbound_cycle)
            if out.get("pushed"):
                logger.info("Synchro CSA sortante : %d résultat(s) remonté(s)", out["pushed"])
        except Exception:  # noqa: BLE001 — resilience : on réessaie au tour suivant
            logger.exception("Cycle sortant CSA échoué (nouvelle tentative au prochain tour)")
        await asyncio.sleep(interval_seconds)

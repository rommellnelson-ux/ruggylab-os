"""Flux sortant RuggyLab → CSA : résultats validés → événements ``labo_resultats``.

Symétrique au flux entrant, par **réconciliation** (pas de hook dans le workflow
de validation) : le worker balaie les ordres d'origine CSA, et pour chaque examen
dont un résultat *libérable* existe, pousse un événement ``labo_resultats`` vers
CSA, puis marque l'item (``csa_pushed_at``) pour ne jamais le repousser.

Le maillon de liaison est l'**échantillon** : un résultat appartient à un ordre
CSA quand ``Result.sample_id == ExamOrder.sample_id``. On ne dépend donc pas d'un
``ExamOrderItem.result_id`` pré-rempli — au contraire, on le renseigne au passage
(on complète « le bout du fil »).

Résultat *libérable* = validé (technique/bio/auto) **ou** explicitement libéré :
on ne remonte jamais une mesure brute non revue au clinicien.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from app.models import CsaSyncState, ExamOrder, ExamOrderItem, Result, Sample
from app.services.exam_catalog import exam_catalog_entry
from app.utils.datetime_utils import utcnow_naive

from .client import CsaEventSink

logger = logging.getLogger(__name__)


def pending_items(db: Session) -> list[ExamOrderItem]:
    """Items d'ordres CSA, non encore remontés, non annulés, mappés, prélevés.

    Factorisé ici pour être réutilisé par le monitoring (``health``) et le push.
    """
    return (
        db.query(ExamOrderItem)
        .join(ExamOrder, ExamOrderItem.order_id == ExamOrder.id)
        .filter(
            ExamOrder.csa_prescription_id.isnot(None),
            ExamOrder.sample_id.isnot(None),
            ExamOrderItem.csa_pushed_at.is_(None),
            ExamOrderItem.status != "cancelled",
            ~ExamOrderItem.exam_code.like("CSA:%"),  # les non-mappés n'ont pas de résultat
        )
        .all()
    )


def _releasable(result: Result) -> bool:
    """Le résultat est-il en état d'être montré au prescripteur CSA ?"""
    return bool(result.is_validated or result.is_auto_validated or result.released_at is not None)


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _validated_at(result: Result) -> dt.datetime | None:
    """Meilleur horodatage de validation/libération disponible."""
    return (
        result.bio_validated_at
        or result.tech_validated_at
        or result.auto_validated_at
        or result.released_at
    )


def _validation_level(result: Result) -> str:
    """Niveau de validation RÉELLEMENT atteint par ce résultat.

    ``_releasable`` accepte trois états distincts, qu'il serait faux de présenter
    au prescripteur sous une étiquette unique :
      - ``biologique`` : validation biologique humaine (``is_validated``) ;
      - ``auto``       : auto-validation par règles (``is_auto_validated``) ;
      - ``aucune``     : résultat seulement *libéré*. Possible tant que
        ``REQUIRE_VALIDATION_FOR_RELEASE=False`` (mode dégradé). Ce n'est PAS une
        validation biologique et ne doit jamais être publié comme telle.
    """
    if result.is_validated:
        return "biologique"
    if result.is_auto_validated:
        return "auto"
    return "aucune"


# Statut porté au prescripteur, aligné sur le niveau réellement atteint.
_STATUT_PAR_NIVEAU = {
    "biologique": "valide",
    "auto": "valide_auto",
    "aucune": "libere_sans_validation",
}


def _build_payload(order: ExamOrder, item: ExamOrderItem, result: Result) -> dict:
    """Projette un résultat validé en payload ``labo_resultats`` (sans perte).

    Transmet ``data_points`` **tel quel** (structure de mesure de RuggyLab) plutôt
    qu'un aplatissement valeur/unité qui trahirait les examens multi-analytes.
    """
    entry = exam_catalog_entry(item.exam_code) or {}
    niveau = _validation_level(result)
    return {
        "prescription_id": order.csa_prescription_id,
        "exam_code": item.exam_code,
        "exam_label": item.exam_label or entry.get("label"),
        "loinc": entry.get("loinc"),
        "result_type": result.result_type,
        "data_points": result.data_points,
        "flags": result.flags,
        "is_critical": bool(result.is_critical),
        "bioref": {
            "status": result.bioref_status,
            "reference_range": result.bioref_reference_range,
            "comment": result.bioref_comment,
            "source": result.bioref_source,
        },
        "ruggylab_result_id": result.id,
        "ruggylab_validator_id": result.validator_id,
        "valide_le": _iso(_validated_at(result)),
        "statut": _STATUT_PAR_NIVEAU[niveau],
        # Niveau de validation explicite : le prescripteur doit pouvoir
        # distinguer une validation biologique d'une libération en mode dégradé.
        "validation": {
            "niveau": niveau,
            "mode_degrade": niveau == "aucune",
            "valide_par_id": result.validator_id,
            "bio_validated_at": _iso(result.bio_validated_at),
            "tech_validated_at": _iso(result.tech_validated_at),
            "auto_validated_at": _iso(result.auto_validated_at),
            "released_at": _iso(result.released_at),
        },
    }


def _same_patient(db: Session, order: ExamOrder) -> bool:
    """L'échantillon rattaché appartient-il bien au patient de l'ordre ?

    Garde-fou de cohérence patient au *dernier* point avant publication externe.
    L'API de rattachement (``POST /exam-orders/{id}/collect``) vérifie déjà
    ``sample.patient_id == order.patient_id``, mais le flux sortant publie un
    résultat sous une identité chez un tiers (CSA) : il ne doit dépendre d'aucune
    garantie posée en amont. Toute incohérence — échantillon absent ou
    appartenant à un autre patient — bloque la publication (fail-closed).
    """
    patient_id = db.query(Sample.patient_id).filter(Sample.id == order.sample_id).scalar()
    if patient_id is None or patient_id != order.patient_id:
        # Identifiants techniques uniquement : aucune donnée nominative en journal.
        logger.error(
            "csa_sync.outbound.patient_mismatch order_id=%s sample_id=%s "
            "order_patient_id=%s sample_patient_id=%s — publication bloquée",
            order.id,
            order.sample_id,
            order.patient_id,
            patient_id,
        )
        return False
    return True


def _find_result(db: Session, order: ExamOrder, item: ExamOrderItem) -> Result | None:
    """Résultat libérable de cet examen, rattaché à l'échantillon de l'ordre.

    Ne renvoie jamais un résultat si la cohérence patient n'est pas démontrée.
    """
    if order.sample_id is None:
        return None
    if not _same_patient(db, order):
        return None
    candidates = (
        db.query(Result)
        .filter(Result.sample_id == order.sample_id, Result.exam_code == item.exam_code)
        .order_by(Result.id.desc())
        .all()
    )
    for result in candidates:
        if _releasable(result):
            return result
    return None


def push_results(db: Session, client: CsaEventSink) -> dict:
    """Un cycle sortant : pour chaque item CSA non poussé dont le résultat est
    libérable, pousse ``labo_resultats`` et marque l'item. Idempotent.

    ``client`` expose ``push_event(kind, source_item_id, payload)``.
    """
    items = pending_items(db)
    pushed = 0
    last_error: str | None = None
    for item in items:
        order = item.order
        result = _find_result(db, order, item)
        if result is None:
            continue
        source_item_id = f"{order.csa_prescription_id}:{item.exam_code}"
        try:
            client.push_event("labo_resultats", source_item_id, _build_payload(order, item, result))
        except Exception as exc:  # noqa: BLE001 — resilience : on réessaiera au prochain tour
            last_error = f"{source_item_id}: {exc}"
            logger.exception(
                "Échec de remontée résultat CSA (%s), réessai au prochain cycle", source_item_id
            )
            continue
        # Succès : on complète le fil et on marque l'idempotence.
        item.result_id = result.id
        item.status = "resulted"
        item.csa_pushed_at = utcnow_naive()
        pushed += 1

    # Observabilité (I4) : trace du cycle sortant sur la ligne d'état unique.
    state = db.get(CsaSyncState, 1)
    if state is None:
        state = CsaSyncState(id=1)
        db.add(state)
    state.last_outbound_run_at = utcnow_naive()
    state.last_outbound_error = last_error
    state.pushed_count = (state.pushed_count or 0) + pushed

    db.commit()
    return {"pushed": pushed, "error": last_error}


def run_outbound_cycle() -> dict:
    """Ouvre une session + un client CSA et exécute un cycle sortant."""
    from app.db.session import SessionLocal

    from .client import build_client_from_settings

    client = build_client_from_settings()
    db = SessionLocal()
    try:
        return push_results(db, client)
    finally:
        db.close()
        client.close()

"""Cloisonnement RBAC de l'accès aux dossiers patient par unité / service.

Règle métier :
  - ADMIN et OFFICER (encadrement) : accès à tous les dossiers.
  - Agent (TECHNICIAN) sans unité (``unit`` NULL) : transversal → accès à tous.
  - Agent rattaché à une unité : accès aux patients de SA propre unité, plus
    les patients sans unité (pool partagé / non encore affectés).

L'accès hors périmètre est refusé (403) et journalisé par l'appelant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from app.models import ExamOrder, Patient, Result, Sample, User, UserRole


def _is_unrestricted(user: User) -> bool:
    """True si l'utilisateur voit tous les dossiers (encadrement ou transversal)."""
    return user.role in (UserRole.ADMIN, UserRole.OFFICER) or user.unit is None


def can_access_unit(user: User, unit: str | None) -> bool:
    """Indique si ``user`` peut accéder à une ressource rattachée à ``unit``."""
    if _is_unrestricted(user):
        return True
    return unit is None or unit == user.unit


def can_access_patient(user: User, patient: Patient) -> bool:
    """Indique si ``user`` est autorisé à consulter ``patient``."""
    return can_access_unit(user, patient.unit)


def apply_patient_scope(query: Any, user: User) -> Any:
    """Restreint une requête ``Patient`` au périmètre autorisé pour ``user``."""
    if _is_unrestricted(user):
        return query
    return query.filter(or_(Patient.unit.is_(None), Patient.unit == user.unit))


def can_access_sample(user: User, sample: Sample) -> bool:
    """Autorisation d'accès à un échantillon via le périmètre de son patient."""
    if _is_unrestricted(user):
        return True
    if sample.patient is None:
        return True
    return can_access_patient(user, sample.patient)


def apply_sample_patient_scope(query: Any, user: User) -> Any:
    """Restreint une requête ``Sample`` au périmètre patient autorisé."""
    if _is_unrestricted(user):
        return query
    return query.outerjoin(Patient, Sample.patient_id == Patient.id).filter(
        or_(Patient.id.is_(None), Patient.unit.is_(None), Patient.unit == user.unit)
    )


def can_access_result(user: User, result: Result) -> bool:
    """Autorisation d'accès aux données cliniques d'un résultat (via son patient).

    Un résultat sans patient rattaché ne porte pas de PII cloisonnable → autorisé.
    """
    if _is_unrestricted(user):
        return True
    patient = result.sample.patient if result.sample else None
    if patient is None:
        return True
    return patient.unit is None or patient.unit == user.unit


def apply_result_patient_scope(
    query: Any,
    user: User,
    *,
    patient_joined: bool = False,
) -> Any:
    """Restreint une requête ``Result`` au périmètre patient autorisé pour ``user``.

    Inclut les résultats sans patient rattaché (pas de PII à cloisonner).
    ``patient_joined`` évite de répéter les jointures pour les rapports qui les
    ont déjà établies afin de sélectionner des colonnes patient.
    """
    if _is_unrestricted(user):
        return query
    if not patient_joined:
        query = query.outerjoin(Sample, Result.sample_id == Sample.id).outerjoin(
            Patient, Sample.patient_id == Patient.id
        )
    return query.filter(
        or_(Patient.id.is_(None), Patient.unit.is_(None), Patient.unit == user.unit)
    )


def can_access_order(user: User, order: ExamOrder) -> bool:
    """Autorisation d'accès à une prescription d'examens (via son patient)."""
    if _is_unrestricted(user):
        return True
    patient = order.patient  # FK patient non nullable : toujours présent
    return patient.unit is None or patient.unit == user.unit


def apply_order_patient_scope(query: Any, user: User) -> Any:
    """Restreint une requête ``ExamOrder`` au périmètre patient autorisé pour ``user``."""
    if _is_unrestricted(user):
        return query
    return query.join(Patient, ExamOrder.patient_id == Patient.id).filter(
        or_(Patient.unit.is_(None), Patient.unit == user.unit)
    )

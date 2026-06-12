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

from app.models import Patient, User, UserRole


def _is_unrestricted(user: User) -> bool:
    """True si l'utilisateur voit tous les dossiers (encadrement ou transversal)."""
    return user.role in (UserRole.ADMIN, UserRole.OFFICER) or user.unit is None


def can_access_patient(user: User, patient: Patient) -> bool:
    """Indique si ``user`` est autorisé à consulter ``patient``."""
    if _is_unrestricted(user):
        return True
    # Agent rattaché : son unité, ou les patients non affectés
    return patient.unit is None or patient.unit == user.unit


def apply_patient_scope(query: Any, user: User) -> Any:
    """Restreint une requête ``Patient`` au périmètre autorisé pour ``user``."""
    if _is_unrestricted(user):
        return query
    return query.filter(or_(Patient.unit.is_(None), Patient.unit == user.unit))

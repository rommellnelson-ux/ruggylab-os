"""Tests — validation non bloquante à la publication (politique effectif réduit).

Par défaut, un résultat non validé reste publiable (compte-rendu « provisoire ») ;
une valeur critique non prise en charge reste, elle, bloquante (sécurité patient).
Le réglage REQUIRE_VALIDATION_FOR_RELEASE rétablit le mode ISO strict.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.reports import _ensure_releasable_result
from app.core.config import settings
from app.models import Result


def _result(*, is_validated=False, is_critical=False, critical_ack_at=None) -> Result:
    r = Result()
    r.is_validated = is_validated
    r.is_critical = is_critical
    r.critical_ack_at = critical_ack_at
    return r


def test_unvalidated_is_releasable_by_default():
    # Effectif réduit : la validation ne bloque pas la publication.
    _ensure_releasable_result(_result(is_validated=False))  # ne lève pas


def test_unvalidated_blocked_when_strict(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_VALIDATION_FOR_RELEASE", True)
    with pytest.raises(HTTPException) as exc:
        _ensure_releasable_result(_result(is_validated=False))
    assert exc.value.status_code == 409


def test_critical_unacknowledged_always_blocks():
    # Sécurité patient : indépendant de la validation.
    with pytest.raises(HTTPException) as exc:
        _ensure_releasable_result(
            _result(is_validated=False, is_critical=True, critical_ack_at=None)
        )
    assert exc.value.status_code == 409


def test_critical_acknowledged_is_releasable():
    _ensure_releasable_result(
        _result(is_validated=False, is_critical=True, critical_ack_at=dt.datetime.now())
    )  # ne lève pas

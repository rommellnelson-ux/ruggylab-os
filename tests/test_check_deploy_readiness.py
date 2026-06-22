"""Garde-fou : le script de prêt-au-déploiement reste importable et cohérent."""

from __future__ import annotations

import importlib


def test_readiness_module_imports():
    mod = importlib.import_module("scripts.check_deploy_readiness")
    assert callable(mod.main)
    assert callable(mod.check_secrets)
    assert callable(mod.check_database)


def test_weak_secret_is_flagged(monkeypatch):
    mod = importlib.import_module("scripts.check_deploy_readiness")
    from app.core.config import settings

    monkeypatch.setattr(settings, "SECRET_KEY", "short")
    monkeypatch.setattr(settings, "FIRST_SUPERUSER_PASSWORD", "change_me_admin_password")
    mod._fail = 0
    mod.check_secrets()
    assert mod._fail == 2  # SECRET_KEY trop court + mot de passe par défaut

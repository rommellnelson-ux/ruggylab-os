"""Garde-fou : le script de smoke test UAT reste importable (pas de rot)."""

from __future__ import annotations

import importlib


def test_uat_smoke_module_imports():
    mod = importlib.import_module("scripts.uat_smoke")
    # Le point d'entrée et les bornes de configuration existent.
    assert callable(mod.main)
    assert mod.API.endswith("/api/v1")

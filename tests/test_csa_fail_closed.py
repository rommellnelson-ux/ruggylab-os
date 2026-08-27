"""Tests — l'intégration CSA est INERTE par défaut (§4, gate pré-fusion).

La revue des politiques RLS de CSA Plateau a montré que le compte technique
`RUGGYLAB` est sur-privilégié côté CSA (voir docs/INTEGRATION_CSA_RUNBOOK.md,
§1.2). Tant que ce point n'est pas corrigé **dans le dépôt csa-plateau**, la
seule garantie qui tient côté RuggyLab est que l'intégration ne peut pas
s'activer toute seule.

Ces tests verrouillent cette garantie : par défaut, aucun appel réseau n'est
possible, et l'activation exige une configuration externe complète.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.csa_sync import client as csa_client


def _settings(**over) -> Settings:
    base = {
        "SECRET_KEY": "x" * 40,
        "FIRST_SUPERUSER_PASSWORD": "AVeryStrongPassword123!",
    }
    base.update(over)
    return Settings(**base)


# ── inertie par défaut ──────────────────────────────────────────────────────


def test_integration_is_disabled_by_default():
    """Défaut du dépôt : le flux CSA est éteint."""
    assert _settings().CSA_SYNC_ENABLED is False


def test_no_credential_is_shipped_in_defaults():
    """Aucun réglage de connexion n'a de valeur par défaut exploitable."""
    settings = _settings()
    for name in ("CSA_SUPABASE_URL", "CSA_SUPABASE_ANON_KEY", "CSA_RUGGYLAB_PASSWORD"):
        assert getattr(settings, name) == "", f"{name} ne doit pas être pré-rempli dans le code"


def test_env_example_ships_no_concrete_project_key():
    """`.env.example` est public : il décrit la forme, jamais une vraie valeur."""
    from pathlib import Path

    raw = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    line = next(ligne for ligne in raw.splitlines() if ligne.startswith("CSA_SUPABASE_ANON_KEY="))
    valeur = line.split("=", 1)[1].strip()
    assert not valeur.startswith("sb_publishable_"), (
        "une clé de projet concrète a été réintroduite dans .env.example"
    )
    assert not valeur.startswith("sb_secret_"), "clé privilégiée dans .env.example"
    assert valeur == "replace-with-project-anon-key"


# ── refus d'activation sans configuration externe ───────────────────────────


@pytest.mark.parametrize(
    "absent",
    [
        "CSA_SUPABASE_URL",
        "CSA_SUPABASE_ANON_KEY",
        "CSA_RUGGYLAB_EMAIL",
        "CSA_RUGGYLAB_PASSWORD",
    ],
)
def test_client_refuses_to_build_when_a_setting_is_missing(absent, monkeypatch):
    """Chaque réglage requis est individuellement bloquant, avant tout réseau."""
    complet = {
        "CSA_SUPABASE_URL": "https://example.supabase.co",
        "CSA_SUPABASE_ANON_KEY": "anon-key",
        "CSA_RUGGYLAB_EMAIL": "ruggylab@example.test",
        "CSA_RUGGYLAB_PASSWORD": "un-mot-de-passe",
    }
    complet[absent] = ""
    monkeypatch.setattr(csa_client, "settings", _settings(**complet))

    assert csa_client.missing_csa_settings() == [absent]
    with pytest.raises(RuntimeError, match=absent):
        csa_client.build_client_from_settings()


def test_blank_password_is_treated_as_missing(monkeypatch):
    """Un mot de passe fait d'espaces ne vaut pas configuration."""
    monkeypatch.setattr(
        csa_client,
        "settings",
        _settings(
            CSA_SUPABASE_URL="https://example.supabase.co",
            CSA_SUPABASE_ANON_KEY="anon-key",
            CSA_RUGGYLAB_EMAIL="ruggylab@example.test",
            CSA_RUGGYLAB_PASSWORD="   ",
        ),
    )
    assert "CSA_RUGGYLAB_PASSWORD" in csa_client.missing_csa_settings()
    with pytest.raises(RuntimeError):
        csa_client.build_client_from_settings()


def test_default_settings_cannot_build_a_client(monkeypatch):
    """Avec les valeurs par défaut du dépôt, aucun client n'est constructible."""
    monkeypatch.setattr(csa_client, "settings", _settings())
    assert len(csa_client.missing_csa_settings()) == 4
    with pytest.raises(RuntimeError):
        csa_client.build_client_from_settings()


def test_scheduler_does_not_start_worker_when_disabled():
    """Le worker n'est câblé que derrière `CSA_SYNC_ENABLED`.

    Vérifié sur la source : la construction de la tâche est bien gardée, donc
    un process scheduler par défaut ne planifie aucun cycle CSA.
    """
    from pathlib import Path

    source = (
        (Path(__file__).resolve().parents[1] / "app" / "scheduler.py")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    ligne_garde = next(i for i, line in enumerate(source) if "settings.CSA_SYNC_ENABLED" in line)
    ligne_worker = next(i for i, line in enumerate(source) if "periodic_csa_sync(" in line)
    assert ligne_garde < ligne_worker, "le worker CSA doit rester derrière la garde"
    assert source[ligne_garde].strip().startswith("if "), "la garde doit être une condition"

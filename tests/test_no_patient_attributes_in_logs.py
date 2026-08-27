"""Tests — aucun attribut patient brut dans les journaux cliniques/financiers.

Traite les alertes CodeQL hautes `py/clear-text-logging-sensitive-data` des
chemins cliniques et financiers, soumis à l'exigence renforcée : aucune donnée
patient brute, aucun contenu de prescription, aucun identifiant nominatif.
"""

from __future__ import annotations

import logging

import pytest

from app.services.prescription_scanner import _age_band

# ── tranche d'âge : jamais l'âge exact ──────────────────────────────────────


@pytest.mark.parametrize(
    "age,attendu",
    [
        (0, "0-1"),
        (1.5, "0-1"),
        (2, "2-11"),
        (11, "2-11"),
        (12, "12-17"),
        (17, "12-17"),
        (18, "18-64"),
        (64, "18-64"),
        (65, "65+"),
        (98, "65+"),
        (None, "inconnu"),
    ],
)
def test_age_band_buckets(age, attendu):
    assert _age_band(age) == attendu


def test_age_band_never_returns_the_exact_age():
    """Deux âges distincts d'une même tranche deviennent indiscernables."""
    assert _age_band(31) == _age_band(52)
    assert "31" not in _age_band(31)


def test_age_band_output_is_a_closed_set():
    """La sortie est un vocabulaire fini : impossible d'y faire fuiter une valeur."""
    valeurs = {_age_band(a) for a in [None, 0, 1, 5, 13, 20, 40, 64, 65, 90, 120]}
    assert valeurs <= {"inconnu", "0-1", "2-11", "12-17", "18-64", "65+"}


# ── ce que les journaux émettent réellement ─────────────────────────────────

_ATTRIBUTS_PATIENT_INTERDITS = {
    "patient_age",
    "patient_name",
    "patient_nom",
    "patient_id",
    "ipp",
    "birth_date",
    "date_naissance",
    "pdf_filename",
    "prescription_date",
}


def _extras(records: list[logging.LogRecord], event: str) -> dict:
    for record in records:
        if record.getMessage() == event:
            return {
                k: v
                for k, v in record.__dict__.items()
                if k not in logging.LogRecord("", 0, "", 0, "", None, None).__dict__
            }
    raise AssertionError(f"journal {event!r} absent")


def test_scanner_log_carries_no_patient_attribute(caplog):
    # Réutilise les constructeurs de la suite existante plutôt que de redéclarer
    # des schémas : le test suit ainsi le modèle réel s'il évolue.
    from app.services.prescription_scanner import PrescriptionScanner
    from tests.test_prescription_scanner import _line, _patient, _request

    request = _request(drugs=[_line("PARACETAMOL", 500, 3, 5)], patient=_patient(age=37))

    with caplog.at_level(logging.INFO, logger="app.services.prescription_scanner"):
        PrescriptionScanner().scan(request)

    extras = _extras(caplog.records, "prescription_scanner.scan")
    for interdit in _ATTRIBUTS_PATIENT_INTERDITS:
        assert interdit not in extras, f"{interdit!r} ne doit pas être journalisé"
    assert extras["patient_age_band"] == "18-64"
    # L'âge exact ne doit apparaître dans aucune valeur du journal.
    assert "37" not in " ".join(str(v) for v in extras.values())

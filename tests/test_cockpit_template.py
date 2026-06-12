"""Tests de cohérence du template cockpit (sans navigateur).

Couvre les régressions front les plus fréquentes : élément de vue manquant ou
fonction JS référencée par un onclick mais non définie. Léger substitut à des
tests Playwright (non disponibles dans cet environnement)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "templates" / "cockpit.html"


@pytest.fixture(scope="module")
def html() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def _is_defined(html: str, fn: str) -> bool:
    """Vrai si ``fn`` est défini comme fonction/const/var dans le script."""
    patterns = [
        rf"function\s+{re.escape(fn)}\s*\(",
        rf"\b(?:const|let|var)\s+{re.escape(fn)}\s*=",
        rf"\b{re.escape(fn)}\s*=\s*(?:async\s*)?function",
        rf"\b{re.escape(fn)}\s*=\s*(?:async\s*)?\(",
    ]
    return any(re.search(p, html) for p in patterns)


class TestNewViewsPresent:
    @pytest.mark.parametrize(
        "marker",
        [
            'id="quality"',  # vue qualité NC/CAPA
            'id="ncTable"',  # liste des NC
            'id="tat"',  # vue Suivi TAT
            'id="tatByExamTable"',  # tableau TAT par examen
            'data-view="tat"',  # bouton de navigation TAT
            'id="registre"',  # vue Registre & Import
            'id="registreCsvText"',  # zone de saisie CSV
            'data-view="registre"',  # bouton de navigation Registre
            'id="biorefTable"',  # référentiel biologique
            'id="biorefTest"',  # sélecteur de test à interpréter
            'id="mappingsTable"',  # unification des vocabulaires
            'id="mapTestExam"',  # outil de test de mapping
            'id="complianceTrendChart"',  # courbe de tendance conformité
            'id="patientUnit"',  # champ unité (création patient)
            'id="userUnit"',  # champ unité (création utilisateur)
            'data-view="quality"',  # bouton de navigation qualité
        ],
    )
    def test_marker_present(self, html: str, marker: str) -> None:
        assert marker in html, f"Élément manquant dans le cockpit : {marker}"


class TestHandlerFunctionsDefined:
    @pytest.mark.parametrize(
        "fn",
        [
            # Module qualité
            "loadQuality",
            "createNonConformity",
            "openNcDetail",
            "transitionNc",
            "addNcAction",
            "completeAction",
            # Conformité avancée
            "loadComplianceTrend",
            "openComplianceReport",
            "_renderComplianceTrend",
            # RBAC / édition patient
            "editPatientUnit",
            # Temps-réel
            "connectNotifications",
            "renderNotifSnapshot",
            "disconnectNotifications",
            # Import en lot / dossier
            "submitBulkImport",
            "openDossier",
            "exportPatientFhir",
            # Suivi TAT
            "loadTat",
            "createTatTarget",
            "deleteTatTarget",
            "seedTatDefaults",
            "_renderTatByDayChart",
            # Registre & import
            "_parseCsv",
            "_registreRows",
            "registreAnalyse",
            "registrePreview",
            "registreImport",
            "_renderRegMonthChart",
            # Référentiel biologique
            "loadBioref",
            "seedBioref",
            "interpretBioref",
            "renderBiorefTable",
            # Unification des vocabulaires
            "loadCodeMappings",
            "renderMappingsTable",
            "seedCodeMappings",
            "deleteMapping",
            "testMapping",
            "loadMappingOrphans",
        ],
    )
    def test_function_defined(self, html: str, fn: str) -> None:
        assert _is_defined(html, fn), f"Fonction JS référencée mais non définie : {fn}"


class TestRealtimeAuthHardening:
    def test_ws_uses_subprotocol_not_url_token(self, html: str) -> None:
        # Le jeton ne doit plus transiter par l'URL du WebSocket
        assert "notifications/ws?token=" not in html
        # Il doit passer par le sous-protocole bearer
        assert "['bearer', token]" in html or '["bearer", token]' in html

    def test_logout_revokes_server_side(self, html: str) -> None:
        assert "/api/v1/login/logout" in html

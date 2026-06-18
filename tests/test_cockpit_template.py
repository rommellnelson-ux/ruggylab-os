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
            'id="resultsKpiPending"',  # KPI critiques à prendre en charge
            'data-result-filter="pending"',  # filtre résultats critiques à traiter
            'id="resultSearch"',  # recherche patient/IPP/code-barres résultats
            'id="resultSort"',  # tri de la liste résultats
            "function renderResultsTable",  # rendu filtré de la liste résultats
            "function setResultSearch",  # recherche dans la liste résultats
            "function setResultSort",  # tri de la liste résultats
            "function _resultContext",  # enrichissement patient/échantillon
            "function exportDisplayedResultsCsv",  # export opérationnel CSV
            "function printDisplayedResults",  # export imprimable/PDF
            "function ackDisplayedCriticals",  # prise en charge groupée
            "function openResultAuditFromList",  # audit accessible depuis une ligne
            "Cette action sera tracée dans l'audit clinique.",  # confirmation batch explicite
            "Affinez la liste avant une prise en charge groupée",  # garde-fou batch large
            "/api/v1/results/cockpit?limit=100",  # liste résultats enrichie côté API
            "/api/v1/results/ack-critical-batch",  # action groupée critiques
            'id="resultDetailPanel"',  # panneau détail résultat
            'id="resultDetailPatient"',  # contexte patient dans le détail
            'id="resultDetailBarcode"',  # contexte échantillon dans le détail
            'id="resultDetailClinicalSummary"',  # synthèse médicale copiable
            'id="resultDetailHistory"',  # antériorités comparables
            'id="resultDetailAudit"',  # timeline clinique/audit
            "function openResultDetail",  # ouverture détail depuis une ligne
            "function _renderResultClinicalAudit",  # rendu timeline clinique
            "function copyResultClinicalSummary",  # copie de synthèse clinique
            "Prendre en charge",  # libellé agent pour le suivi critique
            'id="criticalComplianceTable"',  # rapport valeurs critiques
            'id="criticalComplianceTarget"',  # seuil cible qualité
            'id="criticalComplianceExam"',  # filtre examen
            'id="criticalComplianceUnit"',  # filtre unité
            'id="criticalComplianceSummary"',  # synthèse comité qualité
            'id="critCompLate"',  # KPI hors délai
            "function loadCriticalCompliance",  # chargement conformité critiques
            "function debouncedCriticalComplianceLoad",  # filtres rapport critiques
            "function exportCriticalComplianceCsv",  # export conformité critiques
            "/api/v1/reports/critical-compliance' + params",  # API rapport critiques
            "/api/v1/reports/critical-compliance/export.csv' + params",  # CSV rapport critiques
            "Dans délai",  # statut qualité valeurs critiques
            "Hors délai",  # statut qualité valeurs critiques
            "Synthèse qualité",  # résumé qualité médicale
            'id="complianceTrendChart"',  # courbe de tendance conformité
            'id="patientUnit"',  # champ unité (création patient)
            'id="userUnit"',  # champ unité (création utilisateur)
            'data-view="quality"',  # bouton de navigation qualité
            'class="login-banner"',  # bannière visuelle de connexion
            "/static/branding/RuggyLab_OS.jpg",  # image de marque login
            "/static/ai/malaria_dataset_collector.js?v=",  # évite les anciens assets en cache
            "/api/v1/results/' + resultId + '/detail",  # détail résultat enrichi côté API
            "/api/v1/results/' + resultId + '/history",  # antériorités résultat
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

    def test_notification_state_is_available_during_early_logout(self, html: str) -> None:
        assert "var _notifWs = null;" in html
        assert "var _notifPollTimer = null;" in html

    def test_dashboard_critical_metric_uses_pending_alerts(self, html: str) -> None:
        assert "Critiques à prendre en charge" in html
        assert 'api("/api/v1/critical-alerts/pending"' in html
        assert "$(\"mCritical\").textContent = pendingCriticalCount;" in html


class TestStaticJavascriptAssets:
    def test_malaria_dataset_collector_uses_valid_apostrophe_escaping(self) -> None:
        asset = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "static"
            / "ai"
            / "malaria_dataset_collector.js"
        )
        js = asset.read_text(encoding="utf-8")
        assert "Pas assez d\\\\'échantillons" not in js
        assert "Pas assez d'échantillons annotés pour l'entraînement" in js


class TestKeyboardShortcuts:
    def test_browser_reserved_shortcuts_are_not_overridden(self, html: str) -> None:
        assert "'Ctrl+T':" not in html
        assert "'Ctrl+L':" not in html
        assert "'Ctrl+R':" not in html
        assert "'Ctrl+S':" not in html
        assert "'Ctrl+N':" not in html
        assert "browserReservedCtrlKeys" in html

    def test_app_shortcuts_use_ctrl_alt_combo(self, html: str) -> None:
        assert "'Ctrl+Alt+T': () => toggleTheme()" in html
        assert "<kbd>Ctrl+Alt+T</kbd> - Changer thème" in html

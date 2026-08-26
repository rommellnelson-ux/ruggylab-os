"""
Tests — Module de notifications d'alerte de rupture de stock CMU Côte d'Ivoire
===============================================================================

Couverture :
  - _filter_by_severity : RUPTURE_IMMINENTE → filtre correctement
  - _filter_by_severity : ALERTE_ET_PLUS → inclut ALERTE, ALERTE_CRITIQUE, RUPTURE
  - _filter_by_severity : TOUTES → tout sauf OK
  - _send_webhook : mock urllib → True sur 2xx, False sur 5xx
  - _send_webhook : timeout simulé → False + log erreur
  - notify() WEBHOOK seul : webhook appelé, email non
  - notify() EMAIL seul : email appelé, webhook non
  - notify() BOTH : les deux appelés
  - notify() aucun drug filtré → notifications_sent = 0
  - Endpoint FastAPI via TestClient : status 200, NotificationResult valide
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.db.session as db_session
from app.core.config import settings
from app.db.base import Base
from app.main import create_app
from app.schemas.notification import (
    NotificationChannel,
    NotificationRequest,
    NotificationSeverity,
)
from app.schemas.stock_predictor import (
    AlertLevel,
    DiseaseCategory,
    DrugStockInput,
    PredictionHorizon,
    StockPredictionLine,
)
from app.services.notifier import StockNotifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_line(
    dci: str,
    alert: AlertLevel,
    months: float = 1.5,
) -> StockPredictionLine:
    """Fabrique une StockPredictionLine minimale pour les tests."""
    return StockPredictionLine(
        dci_code=dci,
        disease_category=DiseaseCategory.GENERAL,
        current_stock=100,
        cmm_baseline=50,
        seasonal_coefficient=1.0,
        cmm_seasonal=50.0,
        predicted_stock_at_horizon=25.0,
        months_of_stock_remaining=months,
        estimated_rupture_date=date(2026, 7, 1),
        alert_level=alert,
        reorder_needed=True,
        suggested_order_qty=200,
        reorder_cost_xof=Decimal("50000"),
    )


def _mixed_lines() -> list[StockPredictionLine]:
    """Retourne une liste couvrant tous les niveaux d'alerte."""
    return [
        _make_line("ARTEME", AlertLevel.RUPTURE_IMMINENTE, months=0.5),
        _make_line("AMOXI", AlertLevel.ALERTE_CRITIQUE, months=1.5),
        _make_line("PARA", AlertLevel.ALERTE, months=2.5),
        _make_line("METFO", AlertLevel.OK, months=5.0),
    ]


def _drug(
    dci: str = "ARTEMETHER-LUMEFANTRINE",
    stock: int = 5,
    cmm: int = 100,
) -> DrugStockInput:
    return DrugStockInput(
        dci_code=dci,
        current_stock=stock,
        cmm_units=cmm,
        disease_category=DiseaseCategory.GENERAL,
    )


def _notification_request(
    channel: NotificationChannel = NotificationChannel.WEBHOOK,
    severity: NotificationSeverity = NotificationSeverity.TOUTES,
    webhook_url: str | None = "http://hook.example.com/notify",
    email_to: list[str] | None = None,
    stock: int = 5,
) -> NotificationRequest:
    return NotificationRequest(
        drugs=[_drug(stock=stock)],
        horizon_days=PredictionHorizon.NINETY_DAYS,
        channel=channel,
        severity_filter=severity,
        webhook_url=webhook_url,
        email_to=email_to,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def notifier() -> StockNotifier:
    return StockNotifier()


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test_notif.db"
    settings.TESTING = True
    settings.ENABLE_DH36_LISTENER = False
    settings.SECRET_KEY = "test_secret_key_for_pytest_only_123456"
    settings.FIRST_SUPERUSER = "admin"
    settings.FIRST_SUPERUSER_PASSWORD = "change_me_admin_password"
    settings.FIRST_SUPERUSER_FULL_NAME = "RuggyLab Administrator"
    db_session.configure_database(f"sqlite:///{database_path}")
    Base.metadata.drop_all(bind=db_session.engine)
    Base.metadata.create_all(bind=db_session.engine)

    from app.services.bootstrap import init_db

    init_db()

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=db_session.engine)


def _auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ===========================================================================
# 1. _filter_by_severity
# ===========================================================================


class TestFilterBySeverity:
    def test_rupture_imminente_only(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.RUPTURE_IMMINENTE)
        assert len(result) == 1
        assert all(ln.alert_level == AlertLevel.RUPTURE_IMMINENTE for ln in result)

    def test_rupture_imminente_excludes_alerte(self, notifier: StockNotifier) -> None:
        lines = [_make_line("X", AlertLevel.ALERTE)]
        result = notifier._filter_by_severity(lines, NotificationSeverity.RUPTURE_IMMINENTE)
        assert result == []

    def test_alerte_et_plus_includes_alerte(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.ALERTE_ET_PLUS)
        levels = {ln.alert_level for ln in result}
        assert AlertLevel.ALERTE in levels

    def test_alerte_et_plus_includes_alerte_critique(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.ALERTE_ET_PLUS)
        levels = {ln.alert_level for ln in result}
        assert AlertLevel.ALERTE_CRITIQUE in levels

    def test_alerte_et_plus_includes_rupture(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.ALERTE_ET_PLUS)
        levels = {ln.alert_level for ln in result}
        assert AlertLevel.RUPTURE_IMMINENTE in levels

    def test_alerte_et_plus_excludes_ok(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.ALERTE_ET_PLUS)
        assert all(ln.alert_level != AlertLevel.OK for ln in result)
        assert len(result) == 3  # ALERTE + ALERTE_CRITIQUE + RUPTURE_IMMINENTE

    def test_toutes_excludes_ok(self, notifier: StockNotifier) -> None:
        lines = _mixed_lines()
        result = notifier._filter_by_severity(lines, NotificationSeverity.TOUTES)
        assert all(ln.alert_level != AlertLevel.OK for ln in result)
        assert len(result) == 3

    def test_toutes_empty_when_all_ok(self, notifier: StockNotifier) -> None:
        lines = [_make_line("X", AlertLevel.OK, months=5.0)]
        result = notifier._filter_by_severity(lines, NotificationSeverity.TOUTES)
        assert result == []


# ===========================================================================
# 2. _send_webhook
# ===========================================================================


def _make_payload() -> object:
    """Fabrique un StockAlertNotification minimal."""
    from datetime import datetime

    from app.schemas.notification import DrugAlertSummary, StockAlertNotification

    return StockAlertNotification(
        timestamp=datetime.now(tz=UTC),
        facility_id=None,
        critical_count=1,
        alert_count=0,
        drugs_at_risk=[
            DrugAlertSummary(
                dci_code="ARTEME",
                alert_level=AlertLevel.RUPTURE_IMMINENTE,
                months_remaining=0.5,
                estimated_rupture_date=date(2026, 6, 1),
                suggested_order_qty=300,
                reorder_cost_xof=None,
            )
        ],
        fhir_bundle_url=None,
    )


class TestSendWebhook:
    def test_blocks_private_network_url(self) -> None:
        notifier = StockNotifier()

        with patch(
            "app.services.notifier.safe_post_json",
            side_effect=ValueError("unsafe destination"),
        ) as mock_post:
            result = notifier._send_webhook(
                "http://169.254.169.254/latest/meta-data/",
                _make_payload(),
            )

        assert result is False
        mock_post.assert_called_once()

    def test_returns_true_on_200(self, notifier: StockNotifier) -> None:
        with patch("app.services.notifier.safe_post_json", return_value=200):
            result = notifier._send_webhook("http://example.com/hook", _make_payload())  # type: ignore[arg-type]
        assert result is True

    def test_returns_true_on_201(self, notifier: StockNotifier) -> None:
        with patch("app.services.notifier.safe_post_json", return_value=201):
            result = notifier._send_webhook("http://example.com/hook", _make_payload())  # type: ignore[arg-type]
        assert result is True

    def test_returns_false_on_500(self, notifier: StockNotifier) -> None:
        with patch("app.services.notifier.safe_post_json", return_value=500):
            result = notifier._send_webhook("http://example.com/hook", _make_payload())  # type: ignore[arg-type]
        assert result is False

    def test_returns_false_on_timeout(self, notifier: StockNotifier) -> None:
        with patch("app.services.notifier.safe_post_json", side_effect=TimeoutError("timed out")):
            result = notifier._send_webhook("http://example.com/hook", _make_payload())  # type: ignore[arg-type]
        assert result is False

    def test_timeout_logs_error(
        self, notifier: StockNotifier, caplog: pytest.LogCaptureFixture
    ) -> None:

        with patch("app.services.notifier.safe_post_json", side_effect=TimeoutError("timed out")):
            with caplog.at_level("ERROR", logger="app.services.notifier"):
                notifier._send_webhook("http://example.com/hook", _make_payload())  # type: ignore[arg-type]
        assert any("error" in r.message.lower() for r in caplog.records)


# ===========================================================================
# 3. notify() — routing des canaux
# ===========================================================================


class TestNotifyChannelRouting:
    """Vérifie que notify() appelle les bons canaux selon la configuration."""

    def _make_notifier_with_mocks(
        self,
        webhook_ok: bool = True,
        email_ok: bool = True,
    ) -> tuple[StockNotifier, MagicMock, MagicMock]:
        notifier = StockNotifier()
        mock_webhook = MagicMock(return_value=webhook_ok)
        mock_email = MagicMock(return_value=email_ok)
        notifier._send_webhook = mock_webhook  # type: ignore[method-assign]
        notifier._send_email = mock_email  # type: ignore[method-assign]
        return notifier, mock_webhook, mock_email

    def test_webhook_only_calls_webhook_not_email(self) -> None:
        notifier, mock_webhook, mock_email = self._make_notifier_with_mocks()
        req = _notification_request(
            channel=NotificationChannel.WEBHOOK,
            webhook_url="http://hook.example.com",
            stock=5,  # stock faible → RUPTURE → filtré par TOUTES
        )
        notifier.notify(req)
        mock_webhook.assert_called_once()
        mock_email.assert_not_called()

    def test_email_only_calls_email_not_webhook(self) -> None:
        notifier, mock_webhook, mock_email = self._make_notifier_with_mocks()
        req = _notification_request(
            channel=NotificationChannel.EMAIL,
            webhook_url=None,
            email_to=["pharmacien@hopital.ci"],
            stock=5,
        )
        notifier.notify(req)
        mock_email.assert_called_once()
        mock_webhook.assert_not_called()

    def test_both_calls_webhook_and_email(self) -> None:
        notifier, mock_webhook, mock_email = self._make_notifier_with_mocks()
        req = _notification_request(
            channel=NotificationChannel.BOTH,
            webhook_url="http://hook.example.com",
            email_to=["pharmacien@hopital.ci"],
            stock=5,
        )
        notifier.notify(req)
        mock_webhook.assert_called_once()
        mock_email.assert_called_once()

    def test_no_drugs_notified_when_all_ok(self) -> None:
        """Aucune notification si tous les stocks sont OK après filtre."""
        notifier, mock_webhook, mock_email = self._make_notifier_with_mocks()
        req = _notification_request(
            channel=NotificationChannel.WEBHOOK,
            severity=NotificationSeverity.RUPTURE_IMMINENTE,
            webhook_url="http://hook.example.com",
            stock=50_000,  # stock très élevé → OK
        )
        result = notifier.notify(req)
        assert result.notifications_sent == 0
        assert result.drugs_notified == []
        mock_webhook.assert_not_called()
        mock_email.assert_not_called()

    def test_notifications_sent_count(self) -> None:
        notifier, _, _ = self._make_notifier_with_mocks(webhook_ok=True, email_ok=True)
        req = _notification_request(
            channel=NotificationChannel.BOTH,
            webhook_url="http://hook.example.com",
            email_to=["pharmacien@hopital.ci"],
            stock=5,
        )
        result = notifier.notify(req)
        assert result.notifications_sent == 2
        assert "WEBHOOK" in result.channels_used
        assert "EMAIL" in result.channels_used

    def test_failed_webhook_adds_error(self) -> None:
        notifier, _, _ = self._make_notifier_with_mocks(webhook_ok=False)
        submitted_url = "http://hook.example.com/private-path"
        req = _notification_request(
            channel=NotificationChannel.WEBHOOK,
            webhook_url=submitted_url,
            stock=5,
        )
        result = notifier.notify(req)
        assert result.notifications_sent == 0
        assert result.errors == ["Échec envoi webhook."]
        assert submitted_url not in str(result.errors)

    def test_drugs_notified_contains_dci_codes(self) -> None:
        notifier, _, _ = self._make_notifier_with_mocks()
        req = _notification_request(
            channel=NotificationChannel.WEBHOOK,
            webhook_url="http://hook.example.com",
            stock=5,
        )
        result = notifier.notify(req)
        assert len(result.drugs_notified) > 0
        assert all(isinstance(code, str) for code in result.drugs_notified)


# ===========================================================================
# 4. Endpoint FastAPI via TestClient
# ===========================================================================


class TestStockNotificationEndpoint:
    """Tests d'intégration via FastAPI TestClient."""

    def test_notify_endpoint_returns_200(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        with patch("app.services.notifier.StockNotifier._send_webhook", return_value=True):
            resp = client.post(
                "/api/v1/stock/notify",
                json={
                    "drugs": [
                        {
                            "dci_code": "ARTEMETHER-LUMEFANTRINE",
                            "current_stock": 5,
                            "cmm_units": 100,
                            "disease_category": "ANTIMALARIAL",
                        }
                    ],
                    "horizon_days": 90,
                    "channel": "WEBHOOK",
                    "severity_filter": "TOUTES",
                    "webhook_url": "http://hook.example.com/notify",
                },
                headers=headers,
            )
        assert resp.status_code == 200, resp.text

    def test_notify_endpoint_returns_notification_result_schema(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        with patch("app.services.notifier.StockNotifier._send_webhook", return_value=True):
            resp = client.post(
                "/api/v1/stock/notify",
                json={
                    "drugs": [
                        {
                            "dci_code": "ARTEMETHER-LUMEFANTRINE",
                            "current_stock": 5,
                            "cmm_units": 100,
                            "disease_category": "ANTIMALARIAL",
                        }
                    ],
                    "horizon_days": 90,
                    "channel": "WEBHOOK",
                    "severity_filter": "TOUTES",
                    "webhook_url": "http://hook.example.com/notify",
                },
                headers=headers,
            )
        data = resp.json()
        # Vérifie la structure NotificationResult
        assert "prediction_summary" in data
        assert "notifications_sent" in data
        assert "channels_used" in data
        assert "drugs_notified" in data
        assert "errors" in data

    def test_notify_endpoint_without_auth_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/stock/notify",
            json={
                "drugs": [
                    {
                        "dci_code": "ARTEMETHER-LUMEFANTRINE",
                        "current_stock": 5,
                        "cmm_units": 100,
                    }
                ],
                "horizon_days": 90,
                "channel": "WEBHOOK",
                "severity_filter": "TOUTES",
                "webhook_url": "http://hook.example.com/notify",
            },
        )
        assert resp.status_code == 401

    def test_notify_endpoint_email_channel(self, client: TestClient) -> None:
        headers = _auth_headers(client)
        with patch("app.services.notifier.StockNotifier._send_email", return_value=True):
            resp = client.post(
                "/api/v1/stock/notify",
                json={
                    "drugs": [
                        {
                            "dci_code": "AMOXICILLIN",
                            "current_stock": 10,
                            "cmm_units": 200,
                            "disease_category": "ANTIBIOTIC",
                        }
                    ],
                    "horizon_days": 30,
                    "channel": "EMAIL",
                    "severity_filter": "ALERTE_ET_PLUS",
                    "email_to": ["pharmacien@hopital.ci"],
                },
                headers=headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "notifications_sent" in data

    def test_notify_endpoint_high_stock_no_notifications(self, client: TestClient) -> None:
        """Un stock très élevé → OK → aucune notification."""
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/stock/notify",
            json={
                "drugs": [
                    {
                        "dci_code": "PARACETAMOL",
                        "current_stock": 100000,
                        "cmm_units": 100,
                        "disease_category": "ANALGESIC",
                    }
                ],
                "horizon_days": 90,
                "channel": "WEBHOOK",
                "severity_filter": "RUPTURE_IMMINENTE",
                "webhook_url": "http://hook.example.com/notify",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications_sent"] == 0
        assert data["drugs_notified"] == []


class TestNotifyEndpointSsrfClosure:
    """F-01 — bout en bout : l'endpoint ne peut plus atteindre le réseau interne.

    Le PoC de la baseline (SHA 65e1a02) atteignait 127.0.0.1 via ce chemin.
    Ces tests verrouillent la fermeture au niveau de l'API, pas seulement du
    transport : ils vérifient qu'aucune connexion n'est ouverte, que la réponse
    reste un 200 documenté, et qu'aucune URL interne ne fuit dans le corps.
    """

    _INTERNAL_TARGETS = [
        "http://127.0.0.1/interne/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/hook",
        "http://192.168.1.1/hook",
        "http://[::1]/hook",
        "file:///etc/passwd",
    ]

    @staticmethod
    def _payload(webhook_url: str) -> dict:
        return {
            "drugs": [
                {
                    "dci_code": "ARTEMETHER-LUMEFANTRINE",
                    "current_stock": 5,
                    "cmm_units": 100,
                    "disease_category": "ANTIMALARIAL",
                }
            ],
            "horizon_days": 90,
            "channel": "WEBHOOK",
            "severity_filter": "TOUTES",
            "webhook_url": webhook_url,
        }

    @pytest.mark.parametrize("webhook_url", _INTERNAL_TARGETS)
    def test_internal_target_opens_no_socket(self, client: TestClient, webhook_url: str) -> None:
        headers = _auth_headers(client)
        with patch("app.utils.safe_http.socket.socket") as socket_factory:
            resp = client.post(
                "/api/v1/stock/notify",
                json=self._payload(webhook_url),
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        socket_factory.assert_not_called()
        body = resp.json()
        assert body["notifications_sent"] == 0
        assert "WEBHOOK" not in body["channels_used"]

    def test_refusal_does_not_leak_the_internal_url(self, client: TestClient) -> None:
        """Le message d'erreur ne doit pas renvoyer la cible interne à l'appelant."""
        headers = _auth_headers(client)
        with patch("app.utils.safe_http.socket.socket"):
            resp = client.post(
                "/api/v1/stock/notify",
                json=self._payload("http://169.254.169.254/latest/meta-data/"),
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        assert "169.254.169.254" not in resp.text

"""Chantier runtime : séparation des rôles de process + endpoint /metrics.

Garantit que :
- les propriétés de rôle (`runs_web`/`runs_scheduler`/`runs_analyzer_gateway`)
  gatent correctement les tâches de fond selon `PROCESS_ROLE` ;
- les entrypoints séparés (`app.scheduler`, `app.analyzer_gateway`) sont
  importables et exposent un `main` ;
- les métriques Prometheus sont servies par une route ASGI `/metrics` (et non
  plus par un serveur HTTP secondaire à l'import, incompatible multi-worker).
"""

import importlib

from app.core.config import Settings


def test_process_role_defaults_to_all() -> None:
    s = Settings(PROCESS_ROLE="all")
    assert s.runs_web
    assert s.runs_scheduler
    assert s.runs_analyzer_gateway


def test_process_role_web_runs_no_singleton() -> None:
    s = Settings(PROCESS_ROLE="web")
    assert s.runs_web
    assert not s.runs_scheduler
    assert not s.runs_analyzer_gateway


def test_process_role_scheduler_only() -> None:
    s = Settings(PROCESS_ROLE="scheduler")
    assert s.runs_scheduler
    assert not s.runs_web
    assert not s.runs_analyzer_gateway


def test_process_role_analyzer_gateway_only() -> None:
    s = Settings(PROCESS_ROLE="analyzer-gateway")
    assert s.runs_analyzer_gateway
    assert not s.runs_web
    assert not s.runs_scheduler


def test_entrypoint_modules_importable() -> None:
    for name in ("app.scheduler", "app.analyzer_gateway"):
        module = importlib.import_module(name)
        assert callable(module.main)


def test_metrics_endpoint_served_by_route(client) -> None:  # noqa: ANN001
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    # Le registre par défaut expose toujours python_info ; nos compteurs HTTP
    # apparaissent dès qu'une requête a transité par l'ObservabilityMiddleware.
    body = resp.text
    assert "python_info" in body or "http_requests_total" in body

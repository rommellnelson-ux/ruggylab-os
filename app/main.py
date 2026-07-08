import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.v1.api import api_router
from app.core.caching import init_cache
from app.core.compression import CompressionMiddleware
from app.core.config import settings
from app.core.health_check import HealthCheckService
from app.core.logging_config import configure_logging
from app.core.login_rate_limit import LoginRateLimitMiddleware
from app.core.metrics import render_latest
from app.core.middleware import PoweredByMiddleware
from app.core.observability_middleware import ObservabilityMiddleware, RequestIDMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.user_quota import UserQuotaMiddleware
from app.db.session import get_db
from app.services.bootstrap import init_db
from app.services.interfacing.listener_dh36 import DH36Listener
from app.services.token_cleanup import periodic_token_cleanup
from app.utils.redis_rate_limiter import init_redis_client

logger = logging.getLogger(__name__)

# Initialize observability
configure_logging(
    level="INFO",
    json_logs=not settings.TESTING,
    log_file=None if settings.TESTING else "logs/app.log",
)

# Les métriques Prometheus sont exposées via la route ASGI `/metrics` (voir
# create_app), et non plus par un serveur HTTP secondaire à l'import : ce dernier
# provoquait un conflit de port avec plusieurs workers web (cf. chantier runtime).

# Initialize health check service
_app_start_time = datetime.now(UTC)
health_check_service = HealthCheckService(_app_start_time)

# Initialize cache
if not settings.TESTING:
    try:
        init_cache()
        logger.info("Cache initialized (backend: %s)", settings.CACHE_BACKEND)
    except Exception as exc:
        logger.warning("Failed to initialize cache: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    if not settings.TESTING and settings.requires_security_hardening:
        raise RuntimeError(
            "Security settings are too weak for a non-test environment. Update SECRET_KEY and FIRST_SUPERUSER_PASSWORD."
        )
    # Initialise Redis rate-limiter client when configured
    if not settings.TESTING and settings.REDIS_URL:
        init_redis_client(settings.REDIS_URL)
    init_db()
    import asyncio

    logger.info(
        "Process role: %s (web=%s, scheduler=%s, analyzer-gateway=%s)",
        settings.PROCESS_ROLE,
        settings.runs_web,
        settings.runs_scheduler,
        settings.runs_analyzer_gateway,
    )

    # Listener DH36 : rôle analyzer-gateway uniquement (bind un port → exemplaire
    # unique ; sinon plusieurs workers web se disputeraient le port).
    listener_task = None
    cleanup_task = None
    if not settings.TESTING and settings.runs_analyzer_gateway and settings.ENABLE_DH36_LISTENER:
        listener = DH36Listener(
            host=settings.DH36_LISTENER_HOST,
            port=settings.DH36_LISTENER_PORT,
        )
        try:
            listener_task = asyncio.create_task(listener.start())
        except RuntimeError as exc:
            logger.warning("DH36 listener not started: %s", exc)

    # Purge des jetons : tâche planifiée → rôle scheduler uniquement (singleton ;
    # inutile et redondant de la lancer dans chaque worker web).
    if not settings.TESTING and settings.runs_scheduler:
        cleanup_task = asyncio.create_task(
            periodic_token_cleanup(interval_seconds=3600, keep_days=7)
        )
        logger.info("Periodic refresh-token cleanup task started (every 3600 s).")

    # Fan-out Redis des notifications temps-réel : rôle web uniquement, mais bien
    # dans CHAQUE worker web (chacun sert ses propres clients WebSocket — ce n'est
    # pas une duplication mais le mécanisme qui rend le multi-worker correct).
    notif_sub_task = None
    if not settings.TESTING and settings.runs_web and settings.REDIS_URL:
        try:
            from app.services.redis_notification import (
                enable_redis_fanout,
                redis_subscriber_loop,
            )
            from app.utils.redis_rate_limiter import get_redis_client

            redis_client = get_redis_client()
            if redis_client is not None:
                loop = asyncio.get_running_loop()
                enable_redis_fanout(loop, redis_client)
                notif_sub_task = asyncio.create_task(redis_subscriber_loop(redis_client))
                logger.info("Redis notification fan-out enabled.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis notification fan-out not started: %s", exc)

    try:
        yield
    finally:
        if listener_task:
            listener_task.cancel()
        if cleanup_task:
            cleanup_task.cancel()
        if notif_sub_task:
            notif_sub_task.cancel()
        from app.services.redis_notification import disable_redis_fanout

        disable_redis_fanout()


def _load_template(name: str) -> str:
    """Load an HTML template from disk once at module import time."""
    return (Path(__file__).resolve().parent / "templates" / name).read_text(encoding="utf-8")


# Templates chargés une seule fois au démarrage (pas de relecture disque par requête)
_TPL_COCKPIT = _load_template("cockpit.html")
_TPL_COCKPIT_EXPRESS = _load_template("cockpit_express.html")
_TPL_EHM_MAP = _load_template("ehm_map.html")
_TPL_BENCH_RADAR = _load_template("bench_radar.html")


def create_app() -> FastAPI:
    fastapi_app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    fastapi_app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parent / "static"),
        name="static",
    )

    # Add CORS middleware first
    if settings.CORS_ENABLED:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ALLOW_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=settings.CORS_ALLOW_METHODS,
            allow_headers=settings.CORS_ALLOW_HEADERS,
        )

    # Add observability middleware
    fastapi_app.add_middleware(RequestIDMiddleware)
    fastapi_app.add_middleware(SecurityHeadersMiddleware)
    fastapi_app.add_middleware(LoginRateLimitMiddleware)
    fastapi_app.add_middleware(UserQuotaMiddleware)
    fastapi_app.add_middleware(RateLimitMiddleware)
    fastapi_app.add_middleware(CompressionMiddleware)
    fastapi_app.add_middleware(ObservabilityMiddleware)
    fastapi_app.add_middleware(PoweredByMiddleware)

    # Include main API router
    fastapi_app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @fastapi_app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        return {
            "app": settings.APP_NAME,
            "status": "ok",
            "version": settings.APP_VERSION,
        }

    @fastapi_app.get("/app", response_class=HTMLResponse, tags=["ui"])
    async def cockpit() -> str:
        return _TPL_COCKPIT

    @fastapi_app.get("/app/express", response_class=HTMLResponse, tags=["ui"])
    async def cockpit_express() -> str:
        return _TPL_COCKPIT_EXPRESS

    @fastapi_app.get("/app/bench", response_class=HTMLResponse, tags=["ui"])
    async def bench_radar() -> str:
        return _TPL_BENCH_RADAR

    @fastapi_app.get("/app/map", response_class=HTMLResponse, tags=["ui"])
    async def ehm_map() -> str:
        return _TPL_EHM_MAP

    # Health check endpoints
    @fastapi_app.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, Any]:
        """Liveness probe - check if app is running."""
        return health_check_service.get_liveness()

    @fastapi_app.get("/health/ready", tags=["health"])
    async def readiness(db: Session = Depends(get_db)) -> dict[str, Any]:
        """Readiness probe - check if app is ready to receive traffic."""
        return health_check_service.get_readiness(db)

    @fastapi_app.get("/health", tags=["health"])
    async def health(db: Session = Depends(get_db)) -> dict[str, Any]:
        """Comprehensive health check."""
        health_status = health_check_service.get_health(db, settings.APP_VERSION)
        return health_status.model_dump()

    @fastapi_app.get("/health/metrics", tags=["health"])
    async def metrics_summary() -> dict[str, Any]:
        """Get summary of application metrics."""
        return health_check_service.get_metrics_summary()

    @fastapi_app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Exposition Prometheus (scrutée par monitoring/prometheus.yml : app:8000/metrics)."""
        data, content_type = render_latest()
        return Response(content=data, media_type=content_type)

    @fastapi_app.options("/{path_name:path}", include_in_schema=False)
    async def cors_preflight(path_name: str) -> Response:
        return Response(status_code=200)

    return fastapi_app


app = create_app()

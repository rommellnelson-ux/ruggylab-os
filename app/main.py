import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from app.core.metrics import init_metrics_server
from app.core.middleware import PoweredByMiddleware
from app.core.observability_middleware import ObservabilityMiddleware, RequestIDMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.user_quota import UserQuotaMiddleware
from app.db.session import SessionLocal, get_db
from app.services.bootstrap import init_db
from app.services.interfacing.listener_dh36 import DH36Listener
from app.utils.redis_rate_limiter import init_redis_client

logger = logging.getLogger(__name__)

# Initialize observability
configure_logging(
    level="INFO",
    json_logs=not settings.TESTING,
    log_file=None if settings.TESTING else "logs/app.log",
)

# Start metrics server (on different port from main app)
if not settings.TESTING and settings.METRICS_SERVER_ENABLED:
    try:
        init_metrics_server(port=8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as exc:
        logger.warning("Failed to start metrics server: %s", exc)

# Initialize health check service
_app_start_time = datetime.now(timezone.utc)
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
    listener_task = None
    if not settings.TESTING and settings.ENABLE_DH36_LISTENER:
        listener = DH36Listener(
            host=settings.DH36_LISTENER_HOST,
            port=settings.DH36_LISTENER_PORT,
        )
        import asyncio

        try:
            listener_task = asyncio.create_task(listener.start())
        except RuntimeError as exc:
            logger.warning("DH36 listener not started: %s", exc)
    try:
        yield
    finally:
        if listener_task:
            listener_task.cancel()


def _load_template(name: str) -> str:
    """Load an HTML template from disk once at module import time."""
    return (Path(__file__).resolve().parent / "templates" / name).read_text(encoding="utf-8")


# Templates chargés une seule fois au démarrage (pas de relecture disque par requête)
_TPL_COCKPIT = _load_template("cockpit.html")
_TPL_COCKPIT_EXPRESS = _load_template("cockpit_express.html")
_TPL_EHM_MAP = _load_template("ehm_map.html")


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

    @fastapi_app.options("/{path_name:path}", include_in_schema=False)
    async def cors_preflight(path_name: str) -> Response:
        return Response(status_code=200)

    return fastapi_app


app = create_app()

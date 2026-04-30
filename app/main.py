import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.middleware import PoweredByMiddleware
from app.services.bootstrap import init_db
from app.services.interfacing.listener_dh36 import DH36Listener

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.TESTING and settings.requires_security_hardening:
        raise RuntimeError(
            "Security settings are too weak for a non-test environment. Update SECRET_KEY and FIRST_SUPERUSER_PASSWORD."
        )
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


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(PoweredByMiddleware)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        return {
            "app": settings.APP_NAME,
            "status": "ok",
        }

    @app.get("/app", response_class=HTMLResponse, tags=["ui"])
    async def cockpit() -> str:
        template_path = Path(__file__).resolve().parent / "templates" / "cockpit.html"
        return template_path.read_text(encoding="utf-8")

    return app


app = create_app()

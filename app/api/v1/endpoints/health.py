from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {
        "app": settings.APP_NAME,
        "status": "healthy",
    }

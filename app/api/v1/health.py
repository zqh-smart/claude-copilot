from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(tags=["system"])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
    }

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.observability import build_observability_config

router = APIRouter(tags=["system"])


@router.get("/health")
def healthcheck() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "observability": build_observability_config(settings),
    }

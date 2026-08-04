from fastapi import APIRouter

from app.api.v1.chat_memory import router as chat_memory_router
from app.api.v1.companies import router as companies_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.documents import router as documents_router
from app.api.v1.eval import router as eval_router
from app.api.v1.health import router as health_router
from app.api.v1.research import router as research_router
from app.api.v1.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(documents_router)
api_router.include_router(research_router)
api_router.include_router(companies_router)
api_router.include_router(dashboard_router)
api_router.include_router(eval_router)
api_router.include_router(workflows_router)
api_router.include_router(chat_memory_router)

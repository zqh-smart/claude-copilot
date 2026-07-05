"""Observability bootstrap placeholders for LangSmith and Langfuse."""

from app.core.config import Settings


def build_observability_config(settings: Settings) -> dict[str, object]:
    return {
        "langsmith": {
            "enabled": settings.langsmith_tracing,
            "project": settings.langsmith_project,
        },
        "langfuse": {
            "enabled": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
            "host": settings.langfuse_host,
        },
    }

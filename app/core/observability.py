"""Runtime tracing adapters for LangSmith and Langfuse."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any, ContextManager, Iterator, Protocol

from app.core.config import Settings


@dataclass
class TraceSpan:
    output: dict[str, Any] = field(default_factory=dict)

    def set_output(self, output: dict[str, Any]) -> None:
        self.output = output


class TraceBackendProtocol(Protocol):
    name: str

    def open_span(
        self,
        *,
        name: str,
        span: TraceSpan,
        inputs: dict[str, Any],
        metadata: dict[str, Any],
    ) -> ContextManager[None]: ...


class Observability:
    def __init__(self, backends: list[TraceBackendProtocol] | None = None) -> None:
        self._backends = list(backends or [])

    @property
    def backend_names(self) -> list[str]:
        return [backend.name for backend in self._backends]

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[TraceSpan]:
        span = TraceSpan()
        with ExitStack() as stack:
            for backend in self._backends:
                stack.enter_context(
                    backend.open_span(
                        name=name,
                        span=span,
                        inputs=dict(inputs or {}),
                        metadata=dict(metadata or {}),
                    )
                )
            yield span


class LangSmithTraceBackend:
    name = "langsmith"

    def __init__(self, *, api_key: str, project: str) -> None:
        from langsmith import Client

        self._client = Client(api_key=api_key)
        self._project = project

    @contextmanager
    def open_span(
        self,
        *,
        name: str,
        span: TraceSpan,
        inputs: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Iterator[None]:
        from langsmith.run_helpers import trace

        with trace(
            name,
            run_type="chain",
            inputs=inputs,
            metadata=metadata,
            project_name=self._project,
            client=self._client,
        ) as run:
            try:
                yield
            except Exception as exc:
                run.end(error=f"{type(exc).__name__}: {exc}")
                raise
            else:
                run.end(outputs=span.output)


class LangfuseTraceBackend:
    name = "langfuse"

    def __init__(self, *, public_key: str, secret_key: str, host: str) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    @contextmanager
    def open_span(
        self,
        *,
        name: str,
        span: TraceSpan,
        inputs: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Iterator[None]:
        with self._client.start_as_current_observation(
            name=name,
            as_type="chain",
            input=inputs,
            metadata=metadata,
        ) as observation:
            try:
                yield
            except Exception as exc:
                observation.update(
                    level="ERROR",
                    status_message=f"{type(exc).__name__}: {exc}",
                )
                raise
            else:
                observation.update(output=span.output)


def build_observability(settings: Settings) -> Observability:
    backends: list[TraceBackendProtocol] = []
    if settings.langsmith_tracing and settings.langsmith_api_key:
        backends.append(
            LangSmithTraceBackend(
                api_key=settings.langsmith_api_key,
                project=settings.langsmith_project,
            )
        )
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        backends.append(
            LangfuseTraceBackend(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        )
    return Observability(backends)


def build_observability_config(settings: Settings) -> dict[str, object]:
    return {
        "langsmith": {
            "enabled": bool(settings.langsmith_tracing and settings.langsmith_api_key),
            "project": settings.langsmith_project,
        },
        "langfuse": {
            "enabled": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
            "host": settings.langfuse_host,
        },
        "capture_content": settings.observability_capture_content,
    }

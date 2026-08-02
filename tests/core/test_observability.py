from contextlib import contextmanager

import pytest

from app.api.services.workflow_api_service import WorkflowApiService
from app.core.config import Settings
from app.core.observability import Observability, build_observability, build_observability_config
from src.claude_copilot.schemas.workflows import CompareRequest, CompareResponse


class RecordingBackend:
    name = "recording"

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.flush_count = 0

    @contextmanager
    def open_span(self, *, name, span, inputs, metadata):
        self.events.append(("start", name, inputs, metadata))
        try:
            yield
        except Exception as exc:
            self.events.append(("error", type(exc).__name__))
            raise
        finally:
            self.events.append(("end", dict(span.output)))

    def flush(self) -> None:
        self.flush_count += 1


def test_observability_closes_successful_span_with_output() -> None:
    backend = RecordingBackend()
    observability = Observability([backend])

    with observability.trace("research.preview", inputs={"doc_id": "doc-1"}) as span:
        span.set_output({"grounded": True})

    assert observability.backend_names == ["recording"]
    assert backend.events == [
        ("start", "research.preview", {"doc_id": "doc-1"}, {}),
        ("end", {"grounded": True}),
    ]


def test_observability_closes_error_span_and_reraises() -> None:
    backend = RecordingBackend()
    observability = Observability([backend])

    with pytest.raises(RuntimeError, match="boom"):
        with observability.trace("workflow.compare"):
            raise RuntimeError("boom")

    assert backend.events[-2:] == [("error", "RuntimeError"), ("end", {})]


def test_observability_flushes_configured_backends() -> None:
    backend = RecordingBackend()
    observability = Observability([backend])

    observability.flush()

    assert backend.flush_count == 1


def test_observability_disables_exporters_without_credentials() -> None:
    settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key=None,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )

    observability = build_observability(settings)
    config = build_observability_config(settings)

    assert observability.backend_names == []
    assert config["langsmith"]["enabled"] is False
    assert config["langfuse"]["enabled"] is False
    assert config["capture_content"] is False


def test_workflow_trace_redacts_question_content_by_default(monkeypatch) -> None:
    backend = RecordingBackend()
    service = WorkflowApiService(observability=Observability([backend]))
    monkeypatch.setattr(
        service,
        "_compare",
        lambda _request: CompareResponse(answer_markdown="ok", workflow="comparison_workflow"),
    )

    response = service.compare(
        CompareRequest(doc_id_a="a", doc_id_b="b", question="sensitive question")
    )

    inputs = backend.events[0][2]
    assert response.answer_markdown == "ok"
    assert inputs["question_length"] == len("sensitive question")
    assert "question" not in inputs
    assert backend.events[-1][1]["workflow"] == "comparison_workflow"

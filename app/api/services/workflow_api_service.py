"""Thin wrappers around comparison/report LangGraph workflows for HTTP APIs."""

from __future__ import annotations

from app.core.observability import Observability
from src.claude_copilot.schemas.workflows import (
    CompareRequest,
    CompareResponse,
    ReportOutlineRequest,
    ReportOutlineResponse,
)


class WorkflowApiService:
    def __init__(
        self,
        *,
        observability: Observability | None = None,
        capture_trace_content: bool = False,
    ) -> None:
        self._observability = observability or Observability()
        self._capture_trace_content = capture_trace_content

    def compare(self, request: CompareRequest) -> CompareResponse:
        inputs = {
            "doc_id_a": request.doc_id_a,
            "doc_id_b": request.doc_id_b,
            "period": request.period,
            "metric_keys": request.metric_keys,
            "question_length": len(request.question),
        }
        if self._capture_trace_content:
            inputs["question"] = request.question
        with self._observability.trace("workflow.compare", inputs=inputs) as span:
            response = self._compare(request)
            span.set_output(
                {
                    "workflow": response.workflow,
                    "matrix_rows": len(response.matrix),
                    "warning_count": len(response.warnings),
                }
            )
            return response

    def _compare(self, request: CompareRequest) -> CompareResponse:
        if request.use_workflow:
            from app.workflows.comparison_workflow.graph import graph as comparison_workflow

            result = comparison_workflow.invoke(
                {
                    "doc_id_a": request.doc_id_a,
                    "doc_id_b": request.doc_id_b,
                    "question": request.question,
                    "period": request.period,
                    "metric_keys": request.metric_keys,
                }
            )
            return CompareResponse(
                answer_markdown=str(result.get("answer") or ""),
                matrix=list(result.get("compare_matrix") or []),
                highlights=list(result.get("compare_highlights") or []),
                warnings=list(result.get("warnings") or []),
                workflow="comparison_workflow",
            )

        from app.workflows.comparator.graph import graph as comparator_graph

        result = comparator_graph.invoke(
            {
                "doc_id_a": request.doc_id_a,
                "doc_id_b": request.doc_id_b,
                "question": request.question,
                "period": request.period,
                "metric_keys": request.metric_keys,
            }
        )
        return CompareResponse(
            answer_markdown=str(result.get("answer") or ""),
            matrix=list(result.get("matrix") or []),
            highlights=list(result.get("highlights") or []),
            warnings=list(result.get("warnings") or []),
            workflow="comparator",
        )

    def report_outline(self, request: ReportOutlineRequest) -> ReportOutlineResponse:
        inputs = {
            "doc_id": request.doc_id,
            "top_k": request.top_k,
            "question_length": len(request.question),
        }
        if self._capture_trace_content:
            inputs["question"] = request.question
        with self._observability.trace("workflow.report_outline", inputs=inputs) as span:
            response = self._report_outline(request)
            span.set_output(
                {
                    "workflow": response.workflow,
                    "section_count": len(response.sections),
                    "warning_count": len(response.warnings),
                }
            )
            return response

    def _report_outline(self, request: ReportOutlineRequest) -> ReportOutlineResponse:
        if request.use_workflow:
            from app.workflows.report_workflow.graph import graph as report_workflow

            result = report_workflow.invoke(
                {
                    "doc_id": request.doc_id,
                    "question": request.question,
                    "top_k": request.top_k,
                }
            )
            sections = list(result.get("report_sections") or [])
            return ReportOutlineResponse(
                answer_markdown=str(result.get("answer") or ""),
                sections=sections,
                warnings=list(result.get("warnings") or []),
                workflow="report_workflow",
            )

        from app.workflows.reporting.graph import graph as reporting_graph

        result = reporting_graph.invoke(
            {
                "doc_id": request.doc_id,
                "question": request.question,
                "top_k": request.top_k,
            }
        )
        return ReportOutlineResponse(
            answer_markdown=str(result.get("answer") or ""),
            sections=list(result.get("sections") or []),
            warnings=list(result.get("warnings") or []),
            workflow="reporting",
        )


def get_workflow_api_service() -> WorkflowApiService:
    from app.api.dependencies import get_observability
    from app.core.config import get_settings

    settings = get_settings()
    return WorkflowApiService(
        observability=get_observability(),
        capture_trace_content=settings.observability_capture_content,
    )

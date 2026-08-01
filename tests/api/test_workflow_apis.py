"""Contract tests for thin Compare / Report outline APIs (P7c)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.services.report_artifact_service import (
    ReportArtifact,
    get_report_artifact_service,
)
from app.main import app

client = TestClient(app)


def test_report_export_api_returns_download() -> None:
    service = MagicMock()
    service.export.return_value = ReportArtifact(
        content=b"%PDF-test",
        media_type="application/pdf",
        filename="report.pdf",
    )
    app.dependency_overrides[get_report_artifact_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/report/export",
            json={"doc_id": "doc-1", "format": "pdf"},
        )
    finally:
        app.dependency_overrides.pop(get_report_artifact_service, None)

    assert response.status_code == 200
    assert response.content == b"%PDF-test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="report.pdf"'


def test_report_bundle_export_api_returns_download() -> None:
    service = MagicMock()
    service.export_bundle.return_value = ReportArtifact(
        content=b"<html>bundle</html>",
        media_type="text/html; charset=utf-8",
        filename="bundle.html",
    )
    app.dependency_overrides[get_report_artifact_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/report/export-bundle",
            json={
                "doc_ids": ["doc-2022", "doc-2023"],
                "report_type": "risk",
                "format": "html",
            },
        )
    finally:
        app.dependency_overrides.pop(get_report_artifact_service, None)

    assert response.status_code == 200
    assert response.content == b"<html>bundle</html>"
    service.export_bundle.assert_called_once()


def test_compare_api_uses_comparison_workflow_by_default() -> None:
    fake = {
        "answer": "【§5.4】对比结果",
        "compare_matrix": [{"metric_key": "revenue", "delta": 1.0}],
        "compare_highlights": ["revenue"],
        "warnings": [],
    }
    with patch(
        "app.workflows.comparison_workflow.graph.graph"
    ) as mock_graph:
        mock_graph.invoke = MagicMock(return_value=fake)
        response = client.post(
            "/api/v1/compare",
            json={
                "doc_id_a": "a",
                "doc_id_b": "b",
                "question": "对比两家营收",
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "comparison_workflow"
    assert "§5.4" in payload["answer_markdown"]
    assert payload["matrix"][0]["metric_key"] == "revenue"
    mock_graph.invoke.assert_called_once()


def test_compare_api_can_use_raw_comparator() -> None:
    fake = {
        "answer": "原始矩阵",
        "matrix": [{"metric_key": "net_income"}],
        "highlights": [],
        "warnings": ["ok"],
    }
    with patch("app.workflows.comparator.graph.graph") as mock_graph:
        mock_graph.invoke = MagicMock(return_value=fake)
        response = client.post(
            "/api/v1/compare",
            json={
                "doc_id_a": "a",
                "doc_id_b": "b",
                "use_workflow": False,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "comparator"
    assert payload["answer_markdown"] == "原始矩阵"
    assert payload["warnings"] == ["ok"]


def test_report_outline_api_uses_report_workflow_by_default() -> None:
    fake = {
        "answer": "【§5.5】提纲",
        "report_sections": [{"title": "核心财务指标", "bullets": ["revenue"]}],
        "warnings": [],
    }
    with patch("app.workflows.report_workflow.graph.graph") as mock_graph:
        mock_graph.invoke = MagicMock(return_value=fake)
        response = client.post(
            "/api/v1/report/outline",
            json={"doc_id": "doc-1", "question": "生成提纲报告"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "report_workflow"
    assert "§5.5" in payload["answer_markdown"]
    assert payload["sections"][0]["title"] == "核心财务指标"


def test_report_outline_api_can_use_raw_reporting() -> None:
    fake = {
        "answer": "纯提纲",
        "sections": [{"title": "局限与说明", "bullets": ["MVP"]}],
        "warnings": [],
    }
    with patch("app.workflows.reporting.graph.graph") as mock_graph:
        mock_graph.invoke = MagicMock(return_value=fake)
        response = client.post(
            "/api/v1/report/outline",
            json={"doc_id": "doc-1", "use_workflow": False},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "reporting"
    assert payload["answer_markdown"] == "纯提纲"

"""Portfolio dashboard API contract tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.dependencies import get_financial_data_service, get_graph_store
from app.main import app

client = TestClient(app)


def test_portfolio_dashboard_api_returns_machine_readable_warning() -> None:
    financial = MagicMock()
    graph_store = MagicMock()
    financial.list_companies.return_value = []
    app.dependency_overrides[get_financial_data_service] = lambda: financial
    app.dependency_overrides[get_graph_store] = lambda: graph_store
    try:
        response = client.post(
            "/api/v1/dashboard/portfolio",
            json={"company_ids": ["missing"], "metric_keys": ["revenue"]},
        )
    finally:
        app.dependency_overrides.pop(get_financial_data_service, None)
        app.dependency_overrides.pop(get_graph_store, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["company_ids"] == []
    assert payload["warnings"] == ["company not found: missing"]


def test_portfolio_dashboard_api_rejects_empty_selection() -> None:
    response = client.post(
        "/api/v1/dashboard/portfolio",
        json={"company_ids": [], "metric_keys": ["revenue"]},
    )

    assert response.status_code == 422

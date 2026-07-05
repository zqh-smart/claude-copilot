from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_financial_data_service
from app.api.services.financial_data_service import FinancialDataService
from app.core.db import (
    LocalDocumentRepository,
    LocalFinancialDataRepository,
    LocalParsedDocumentRepository,
    build_company_id,
)
from app.main import app
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    DocumentProcessingStatus,
    DocumentRecord,
    FinancialMetricFact,
    FinancialSchema,
    ParsedDocument,
)


def build_financial_data_service(base_dir: Path) -> FinancialDataService:
    document_repository = LocalDocumentRepository(str(base_dir))
    parsed_repository = LocalParsedDocumentRepository(str(base_dir))
    now = datetime.now(UTC)
    metadata = DocumentMetadata(
        doc_type="annual_report",
        source="test",
        filename="acme-2024.pdf",
        extension=".pdf",
        company="ACME Holdings",
        year=2024,
    )
    document_repository.save(
        DocumentRecord(
            doc_id="acme-2024",
            filename="acme-2024.pdf",
            status=DocumentProcessingStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            storage_path=str(base_dir / "acme-2024.pdf"),
            parsed_path=str(base_dir / "acme-2024.json"),
            metadata=metadata,
        )
    )
    parsed_repository.save(
        ParsedDocument(
            doc_id="acme-2024",
            metadata=metadata,
            financial_schema=FinancialSchema(
                company="ACME Holdings",
                year=2024,
                metric_facts=[
                    FinancialMetricFact(
                        metric_key="revenue",
                        period=str(year),
                        value=value,
                        statement_type="income_statement",
                        unit="millions",
                        currency="USD",
                        source_table_id="income-table",
                        source_table_title="Consolidated statements of income",
                        page_range=(10, 10),
                    )
                    for year, value in [(2022, 100), (2023, 120), (2024, 144)]
                ]
                + [
                    FinancialMetricFact(
                        metric_key="net_income",
                        period="2024",
                        value=24,
                        statement_type="income_statement",
                        unit="millions",
                        currency="USD",
                        source_table_id="income-table",
                    )
                ],
            ),
        )
    )
    return FinancialDataService(
        LocalFinancialDataRepository(document_repository, parsed_repository)
    )


def test_financial_data_api_queries_metrics_and_calculates_trend(tmp_path: Path) -> None:
    service = build_financial_data_service(tmp_path)
    app.dependency_overrides[get_financial_data_service] = lambda: service
    client = TestClient(app)
    company_id = build_company_id("ACME Holdings")

    companies_response = client.get("/api/v1/companies")
    assert companies_response.status_code == 200
    assert companies_response.json() == [
        {
            "company_id": company_id,
            "name": "ACME Holdings",
            "years": [2022, 2023, 2024],
            "document_count": 1,
            "metric_count": 4,
        }
    ]

    metrics_response = client.get(
        f"/api/v1/companies/{company_id}/metrics",
        params={"year": 2024, "statement_type": "income_statement"},
    )
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["count"] == 2
    assert {item["metric_key"] for item in metrics["items"]} == {"revenue", "net_income"}
    assert all(item["period_year"] == 2024 for item in metrics["items"])

    trend_response = client.get(
        f"/api/v1/companies/{company_id}/metrics/revenue/trend"
    )
    assert trend_response.status_code == 200
    trend = trend_response.json()
    assert trend["unit"] == "millions"
    assert trend["currency"] == "USD"
    assert [point["year"] for point in trend["points"]] == [2022, 2023, 2024]
    assert [point["yoy_growth"] for point in trend["points"]] == [None, 0.2, 0.2]
    assert trend["cagr"] == 0.2
    assert trend["warnings"] == []

    app.dependency_overrides.clear()


def test_financial_data_api_returns_404_for_unknown_company(tmp_path: Path) -> None:
    service = build_financial_data_service(tmp_path)
    app.dependency_overrides[get_financial_data_service] = lambda: service
    client = TestClient(app)

    response = client.get("/api/v1/companies/missing/metrics")

    assert response.status_code == 404
    assert response.json()["detail"] == "Company not found: missing"
    app.dependency_overrides.clear()

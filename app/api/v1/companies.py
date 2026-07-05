from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_financial_data_service
from app.api.services.financial_data_service import FinancialDataService
from app.core.errors import CompanyNotFoundError
from src.claude_copilot.schemas.financial_data import (
    CompanySummary,
    FinancialMetricsResponse,
    MetricTrendResponse,
)

router = APIRouter(prefix="/api/v1/companies", tags=["financial-data"])


@router.get("", response_model=list[CompanySummary])
def list_companies(
    service: FinancialDataService = Depends(get_financial_data_service),
) -> list[CompanySummary]:
    return service.list_companies()


@router.get("/{company_id}/metrics", response_model=FinancialMetricsResponse)
def query_company_metrics(
    company_id: str,
    year: int | None = Query(default=None, ge=1900, le=2200),
    metric_key: str | None = Query(default=None, min_length=1),
    statement_type: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=500, ge=1, le=5000),
    service: FinancialDataService = Depends(get_financial_data_service),
) -> FinancialMetricsResponse:
    try:
        return service.query_metrics(
            company_id,
            year=year,
            metric_key=metric_key,
            statement_type=statement_type,
            limit=limit,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{company_id}/metrics/{metric_key}/trend", response_model=MetricTrendResponse)
def get_metric_trend(
    company_id: str,
    metric_key: str,
    start_year: int | None = Query(default=None, ge=1900, le=2200),
    end_year: int | None = Query(default=None, ge=1900, le=2200),
    service: FinancialDataService = Depends(get_financial_data_service),
) -> MetricTrendResponse:
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must be <= end_year")
    try:
        return service.metric_trend(
            company_id,
            metric_key,
            start_year=start_year,
            end_year=end_year,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

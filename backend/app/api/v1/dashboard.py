"""Portfolio comparison and BI dashboard API."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_financial_data_service, get_graph_store
from app.api.services.financial_data_service import FinancialDataService
from app.api.services.portfolio_dashboard_service import PortfolioDashboardService
from app.core.kg import KnowledgeGraphStoreProtocol
from src.claude_copilot.schemas.dashboard import (
    PortfolioDashboardRequest,
    PortfolioDashboardResponse,
)

router = APIRouter(tags=["dashboard"])


@router.post("/api/v1/dashboard/portfolio", response_model=PortfolioDashboardResponse)
def build_portfolio_dashboard(
    request: PortfolioDashboardRequest,
    financial_data: Annotated[FinancialDataService, Depends(get_financial_data_service)],
    graph_store: Annotated[KnowledgeGraphStoreProtocol, Depends(get_graph_store)],
) -> PortfolioDashboardResponse:
    return PortfolioDashboardService(financial_data, graph_store).build(request)

from __future__ import annotations

from collections import defaultdict

from app.core.db import FinancialDataRepositoryProtocol
from app.core.db.serving_facts import (
    candidate_from_observation,
    metric_values_conflict,
    normalize_metric_value,
    resolve_metric_conflict,
)
from app.core.errors import CompanyNotFoundError
from src.claude_copilot.schemas.financial_data import (
    CompanySummary,
    FinancialMetricsResponse,
    MetricGrowthPoint,
    MetricTrendResponse,
)


class FinancialDataService:
    def __init__(self, repository: FinancialDataRepositoryProtocol) -> None:
        self._repository = repository

    def list_companies(self) -> list[CompanySummary]:
        return self._repository.list_companies()

    def query_metrics(
        self,
        company_id: str,
        *,
        year: int | None,
        metric_key: str | None,
        statement_type: str | None,
        limit: int,
    ) -> FinancialMetricsResponse:
        company = self._require_company(company_id)
        items = self._repository.query_metrics(
            company_id,
            year=year,
            metric_key=metric_key,
            statement_type=statement_type,
            limit=limit,
        )
        return FinancialMetricsResponse(
            company=company,
            filters={
                key: value
                for key, value in {
                    "year": year,
                    "metric_key": metric_key,
                    "statement_type": statement_type,
                    "limit": limit,
                }.items()
                if value is not None
            },
            count=len(items),
            items=items,
        )

    def metric_trend(
        self,
        company_id: str,
        metric_key: str,
        *,
        start_year: int | None,
        end_year: int | None,
    ) -> MetricTrendResponse:
        company = self._require_company(company_id)
        observations = self._repository.query_metrics(
            company_id,
            metric_key=metric_key,
            limit=5000,
        )
        observations = [
            item
            for item in observations
            if item.period_year is not None
            and (start_year is None or item.period_year >= start_year)
            and (end_year is None or item.period_year <= end_year)
        ]

        warnings: list[str] = []
        units = sorted({item.unit for item in observations if item.unit})
        currencies = sorted({item.currency for item in observations if item.currency})
        if len(units) > 1:
            warnings.append(f"inconsistent units: {units}")
        if len(currencies) > 1:
            warnings.append(f"inconsistent currencies: {currencies}")

        by_year = defaultdict(list)
        for item in observations:
            if isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
                by_year[item.period_year].append(item)

        selected = []
        for year in sorted(by_year):
            candidates = by_year[year]
            distinct_values = {normalize_metric_value(item.value) for item in candidates}
            if len(distinct_values) > 1:
                period = candidates[0].period
                resolution = resolve_metric_conflict(
                    [candidate_from_observation(item) for item in candidates],
                    metric_key=metric_key,
                    period=period,
                )
                warnings.extend(resolution.warnings)
                winner = next(
                    (
                        item
                        for item in candidates
                        if resolution.winner is not None
                        and item.document_id == resolution.winner.document_id
                        and not metric_values_conflict(item.value, resolution.winner.value)
                    ),
                    candidates[0],
                )
                selected.append(winner)
                continue
            selected.append(candidates[0])

        points: list[MetricGrowthPoint] = []
        previous = None
        for item in selected:
            value = float(item.value)
            yoy_growth = None
            if previous is not None and previous != 0:
                yoy_growth = round((value - previous) / abs(previous), 6)
            points.append(
                MetricGrowthPoint(
                    year=item.period_year,
                    period=item.period,
                    value=value,
                    yoy_growth=yoy_growth,
                    document_id=item.document_id,
                )
            )
            previous = value

        cagr = None
        dimensions_consistent = len(units) <= 1 and len(currencies) <= 1
        if len(points) >= 2 and dimensions_consistent:
            first = points[0]
            last = points[-1]
            elapsed_years = last.year - first.year
            if elapsed_years > 0 and first.value > 0 and last.value > 0:
                cagr = round((last.value / first.value) ** (1 / elapsed_years) - 1, 6)
            elif elapsed_years > 0:
                warnings.append("CAGR requires positive first and last values")

        if not points:
            warnings.append("no numeric yearly observations matched the requested metric")

        return MetricTrendResponse(
            company=company,
            metric_key=metric_key,
            unit=units[0] if len(units) == 1 else None,
            currency=currencies[0] if len(currencies) == 1 else None,
            points=points,
            cagr=cagr,
            warnings=warnings,
            observations=observations,
        )

    def _require_company(self, company_id: str) -> CompanySummary:
        company = self._repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError(f"Company not found: {company_id}")
        return company

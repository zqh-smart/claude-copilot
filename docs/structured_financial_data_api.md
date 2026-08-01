# Structured Financial Data API

The Knowledge Layer exposes financial facts extracted by Document AI through
both local JSON and PostgreSQL repository implementations.

## Endpoints

```text
GET /api/v1/companies
GET /api/v1/companies/{company_id}/metrics
GET /api/v1/companies/{company_id}/metrics/{metric_key}/trend
POST /api/v1/dashboard/portfolio
POST /api/v1/report/export-bundle
```

List companies first to obtain the stable `company_id`.

The portfolio endpoint accepts 1–20 company IDs and up to 10 metric keys. It returns
financial rankings, industry distribution, risk heatmap profiles, and pairwise business
overlap. Financial values come from Serving facts; risk, industry, and business evidence
comes from the configured knowledge-graph backend. Dimension mismatches are returned as warnings.

The report bundle endpoint accepts 1–20 document IDs, `investment` or `risk` report type,
and `html` or `pdf` format. The Report Center maps the selected company and year range to
completed documents before requesting the bundle.

The metrics endpoint accepts:

- `year`
- `metric_key`
- `statement_type`
- `limit` (1–5000)

The trend endpoint accepts `start_year` and `end_year`. It returns numeric
yearly points, YoY growth, CAGR, source observations, and warnings when values
conflict or units/currencies are inconsistent.

## Examples

```bash
curl "http://localhost:8000/api/v1/companies"
curl "http://localhost:8000/api/v1/companies/{company_id}/metrics?metric_key=revenue&year=2024"
curl "http://localhost:8000/api/v1/companies/{company_id}/metrics/revenue/trend?start_year=2022&end_year=2024"
```

Only documents in the `completed` state with a non-empty company name are
included. The `year` filter applies to the year extracted from each metric's
reporting period, not merely to the source document year.

## Retrieval Orchestrator

`POST /api/v1/research/query` now analyzes each question and reports one of
three routing decisions:

- `semantic`: Vector/Qdrant retrieval only.
- `structured`: SQL financial facts only.
- `hybrid`: Vector and SQL retrieval in parallel, followed by evidence fusion.

The response includes `query_analysis`, `hits`, `metrics`, deterministic
`calculations` (YoY/CAGR), and `warnings`. Existing request fields remain
compatible:

```json
{
  "doc_id": "schema-benchmark",
  "question": "Why did net income grow? Analyze the drivers.",
  "top_k": 3
}
```

## Grounded synthesis and critic loop

When `LLM_GROUNDED_SYNTHESIS_ENABLED=true`, the research workflow is:

```text
retrieve → synthesize → critique → revise (when needed) → critique → end
```

The synthesizer may only use evidence IDs from the Vector (`V*`), SQL (`S*`),
and deterministic calculation (`C*`) catalogs. The independent critic checks
numbers, years, units, currencies, causal claims, and citations. A failed
review triggers revision up to `LLM_MAX_REVISIONS`.

The response additionally exposes:

- `synthesis`: structured answer, findings, citations, confidence, limitations.
- `critic`: pass/fail, score, issue list, and audit summary.
- `revision_count`: number of rewrite attempts.
- `grounded`: `true` only after the critic passes.

If synthesis or criticism fails, the API returns a transparent degraded answer
with `grounded=false` and diagnostic warnings.

`POST /api/v1/research/preview` remains as a backward-compatible alias.

## Compare / Report outline (P7c lite)

No report-center UI and no PDF export — Markdown + JSON only.

```text
POST /api/v1/compare
POST /api/v1/report/outline
```

Examples:

```bash
curl -X POST "http://localhost:8000/api/v1/compare" -H "Content-Type: application/json" -d "{\"doc_id_a\":\"<uuid>\",\"doc_id_b\":\"<uuid>\",\"question\":\"对比两家营收\"}"

curl -X POST "http://localhost:8000/api/v1/report/outline" -H "Content-Type: application/json" -d "{\"doc_id\":\"<uuid>\",\"question\":\"生成提纲报告\"}"
```

- `use_workflow=true` (default): `comparison_workflow` / `report_workflow` (§5.4/§5.5 lite)
- `use_workflow=false`: raw `comparator` / `reporting` graphs

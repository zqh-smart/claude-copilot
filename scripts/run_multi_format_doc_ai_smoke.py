from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.parser import ParserRouter
from app.pipeline.feature_pipeline.evaluation import DocumentAIGoldenEvaluator
from app.pipeline.feature_pipeline.schema_mapping import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation import SemanticSegmentationService
from app.pipeline.feature_pipeline.structure_reconstruction import StructureReconstructionService
from app.pipeline.feature_pipeline.table_intelligence import TableIntelligenceService
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument


FIXTURES = [
    Path("data/fixtures/multi_format_smoke/aapl_2023_10k.html"),
    Path("data/fixtures/multi_format_smoke/bmw_group_financial_analysis.xlsx"),
    Path("data/fixtures/multi_format_smoke/bmw_group_financial_analysis_report.docx"),
]

REPORT_PATH = Path("data/reports/multi_format_doc_ai_smoke_report.json")
GOLDEN_PATH = Path("data/golden/document_ai_expectations.json")


def build_metadata(path: Path) -> DocumentMetadata:
    return DocumentMetadata(
        doc_type="annual_report",
        source="smoke_test",
        filename=path.name,
        extension=path.suffix.lower(),
        content_type=None,
        size_bytes=path.stat().st_size,
    )


def run_document_ai(document: ParsedDocument) -> ParsedDocument:
    document = SemanticSegmentationService().segment(document)
    document = TableIntelligenceService().enhance(document)
    document = StructureReconstructionService().reconstruct(document)
    document = FinancialSchemaMappingService().map(document)
    return document


def summarize(document: ParsedDocument, path: Path) -> dict:
    semantic_sections = [section for section in document.sections if section.metadata.get("source") == "semantic_segmentation"]
    table_types = Counter(table.table_type or "unknown" for table in document.tables)
    schema = document.financial_schema

    statements = []
    notes = []
    metric_fact_count = 0
    note_fact_count = 0
    if schema is not None:
        statements = [
            {
                "statement_type": item.statement_type,
                "title": item.title,
                "page_range": item.page_range,
                "metric_keys": sorted(item.metrics.keys())[:10],
            }
            for item in schema.statements
        ]
        notes = [
            {
                "note_number": item.note_number,
                "note_title": item.note_title,
                "note_category": item.note_category,
                "page_range": item.page_range,
            }
            for item in schema.notes
        ]
        metric_fact_count = len(schema.metric_facts)
        note_fact_count = len(schema.note_facts)

    return {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "parse": {
            "route": document.metadata.parse_route,
            "backend": document.metadata.parse_backend,
            "page_count": document.metadata.page_count,
            "parsed_page_range": document.metadata.parsed_page_range,
            "parsed_page_count": document.metadata.parsed_page_count,
        },
        "counts": {
            "sections": len(document.sections),
            "semantic_sections": len(semantic_sections),
            "page_blocks": len(document.page_blocks),
            "tables": len(document.tables),
            "issues": len(document.issues),
            "segments": len(document.segments),
            "schema_statements": len(statements),
            "schema_notes": len(notes),
            "metric_facts": metric_fact_count,
            "note_facts": note_fact_count,
        },
        "semantic_section_types": Counter(section.section_type or "unknown" for section in semantic_sections),
        "top_semantic_sections": [
            {
                "title": section.title,
                "section_type": section.section_type,
                "page_range": [section.page_start, section.page_end],
                "confidence": section.metadata.get("confidence"),
            }
            for section in semantic_sections[:10]
        ],
        "table_types": dict(table_types),
        "top_tables": [
            {
                "table_id": table.table_id,
                "table_type": table.table_type,
                "title": table.title,
                "page": table.page,
                "period_headers": table.period_headers,
                "unit": table.unit,
                "currency": table.currency,
                "normalized_metric_keys": sorted(table.normalized_metrics.keys())[:10],
                "source_section": table.source_section,
            }
            for table in document.tables[:10]
        ],
        "statements": statements[:10],
        "notes": notes[:10],
        "issues": [
            {
                "code": issue.code,
                "severity": issue.severity,
                "page": issue.page,
                "message": issue.message,
            }
            for issue in document.issues[:20]
        ],
    }


def main() -> None:
    router = ParserRouter()
    evaluator = DocumentAIGoldenEvaluator()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    results = []

    for path in FIXTURES:
        if not path.exists():
            results.append({"file": str(path), "error": "missing_fixture"})
            continue

        content = path.read_bytes()
        document = router.parse(
            doc_id=path.stem,
            filename=path.name,
            content=content,
            metadata=build_metadata(path),
        )
        document = run_document_ai(document)
        result = summarize(document, path)
        expected = golden["documents"].get(path.name)
        if expected is None:
            result["golden"] = {
                "passed": False,
                "check_count": 0,
                "checks": [],
                "failures": [f"missing golden expectations for {path.name}"],
            }
        else:
            result["golden"] = evaluator.evaluate(document, expected)
        results.append(result)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    failures = [
        failure
        for result in results
        for failure in result.get("golden", {}).get("failures", [])
    ]
    report = {
        "summary": {
            "document_count": len(results),
            "passed_document_count": sum(
                1 for result in results if result.get("golden", {}).get("passed")
            ),
            "passed": not failures,
            "failure_count": len(failures),
        },
        "documents": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(REPORT_PATH)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

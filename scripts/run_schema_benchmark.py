import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.evaluation.service import ParseEvaluationBenchmarkService
from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
from app.pipeline.feature_pipeline.schema_mapping.service import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation.service import SemanticSegmentationService
from app.pipeline.feature_pipeline.table_intelligence.service import TableIntelligenceService
from app.pipeline.feature_pipeline.structure_reconstruction.service import StructureReconstructionService
from src.claude_copilot.schemas.document import DocumentMetadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf-path",
        type=Path,
        default=Path("data/fixtures/jpmc_audited_financial_statements_2024.pdf"),
    )
    parser.add_argument("--start-page-id", type=int, default=0)
    parser.add_argument("--end-page-id", type=int, default=20)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=Path("data/golden/jpmc_2024_smoke_expectations.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/jpmc_schema_smoke_report.json"),
    )
    parser.add_argument(
        "--parsed-output",
        type=Path,
        default=None,
        help="Optional full ParsedDocument JSON for offline inspection and rule tuning.",
    )
    return parser.parse_args()


def load_expectations(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    pdf_path = args.pdf_path
    content = pdf_path.read_bytes()

    metadata = DocumentMetadata(
        doc_type="financial_statement",
        source="fixture",
        filename=pdf_path.name,
        extension=pdf_path.suffix.lower(),
        company="JPMorgan Chase & Co.",
        year=2024,
    )

    parser = PdfDocumentParser(
        backend_priority=["mineru_pdf", "table_pdf", "native_pdf", "ocr_pdf"],
        mineru_start_page_id=args.start_page_id,
        mineru_end_page_id=args.end_page_id,
    )
    segmentation = SemanticSegmentationService()
    table_intelligence = TableIntelligenceService()
    schema_mapping = FinancialSchemaMappingService()
    benchmark = ParseEvaluationBenchmarkService()
    expectations = load_expectations(args.expectations)

    started_at = time.perf_counter()
    document = parser.parse(doc_id="schema-benchmark", content=content, metadata=metadata)
    document = segmentation.segment(document)
    document = table_intelligence.enhance(document)
    document = StructureReconstructionService().reconstruct(document)
    document = schema_mapping.map(document)
    elapsed_seconds = round(time.perf_counter() - started_at, 2)

    report = benchmark.evaluate(document, expected=expectations)
    report["runtime"] = {
        "elapsed_seconds": elapsed_seconds,
        "start_page_id": args.start_page_id,
        "end_page_id": args.end_page_id,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.parsed_output is not None:
        args.parsed_output.parent.mkdir(parents=True, exist_ok=True)
        args.parsed_output.write_text(
            json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("elapsed_seconds=", elapsed_seconds)
    print("parse_route=", report["document"]["parse_route"])
    print("parse_backend=", report["document"]["parse_backend"])
    print("counts=", report["counts"])
    print("statement_types=", report["coverage"]["statement_types"])
    print("semantic_section_types=", report["coverage"]["semantic_section_types"])
    print("statement_metrics=", report["coverage"]["statement_metrics"])
    print("statement_dimensions=", report["coverage"]["statement_dimensions"])
    print("notes_coverage=", report["coverage"]["notes"])
    print("provenance_coverage=", report["coverage"]["provenance"])
    print("check_count=", len(report["checks"]))
    print("failures=", report["failures"])
    print("output=", str(args.output))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

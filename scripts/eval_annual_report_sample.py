"""Evaluate annual-report PDF parsing on 1–2 real samples."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
from app.pipeline.feature_pipeline.schema_mapping.service import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation.service import SemanticSegmentationService
from app.pipeline.feature_pipeline.structure_reconstruction.service import (
    StructureReconstructionService,
)
from app.pipeline.feature_pipeline.table_intelligence.service import TableIntelligenceService
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument

PDF_ROOT = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
)

SAMPLES = [
    {
        "doc_id": "znz-2021",
        "company": "北京指南针科技发展股份有限公司",
        "year": 2021,
        "filename": "2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf",
    },
    {
        "doc_id": "sl-2021",
        "company": "深圳顺络电子股份有限公司",
        "year": 2021,
        "filename": "2022-02-26__深圳顺络电子股份有限公司__002138__顺络电子__2021年__年度报告.pdf",
    },
]


def summarize(document: ParsedDocument, *, elapsed: float, label: str) -> dict:
    block_distribution: dict[str, int] = {}
    for block in document.page_blocks:
        block_distribution[block.block_type] = block_distribution.get(block.block_type, 0) + 1

    schema = document.financial_schema
    table_types: dict[str, int] = {}
    for table in document.tables:
        key = table.table_type or "unknown"
        table_types[key] = table_types.get(key, 0) + 1

    return {
        "label": label,
        "elapsed_seconds": round(elapsed, 2),
        "parse_route": document.metadata.parse_route,
        "parse_backend": document.metadata.parse_backend,
        "page_count": document.metadata.page_count,
        "parsed_page_count": document.metadata.parsed_page_count,
        "parsed_page_range": document.metadata.parsed_page_range,
        "quality": document.quality.model_dump() if document.quality else None,
        "issue_count": len(document.issues),
        "issues_sample": [issue.model_dump() for issue in document.issues[:8]],
        "raw_text_chars": len(document.raw_text or ""),
        "sections": len(document.sections),
        "page_blocks": len(document.page_blocks),
        "block_distribution": dict(sorted(block_distribution.items())),
        "tables": len(document.tables),
        "table_types": dict(sorted(table_types.items())),
        "table_titles_sample": [t.title for t in document.tables[:8]],
        "semantic_sections": [
            {
                "type": s.section_type,
                "title": s.title,
                "page_range": s.page_range,
                "confidence": s.confidence,
            }
            for s in (schema.semantic_sections if schema else [])
        ],
        "statements": [
            {
                "type": s.statement_type,
                "title": s.title,
                "period_headers": s.period_headers,
                "metric_keys": sorted(s.metrics.keys())[:20],
                "metric_count": len(s.metrics),
            }
            for s in (schema.statements if schema else [])
        ],
        "metric_fact_count": len(schema.metric_facts) if schema else 0,
        "note_count": len(schema.notes) if schema else 0,
        "note_fact_count": len(schema.note_facts) if schema else 0,
        "metrics_index_size": len(schema.metrics_index) if schema else 0,
        "raw_text_preview": (document.raw_text or "")[:800].replace("\n", " "),
    }


def run_doc_ai(document: ParsedDocument) -> ParsedDocument:
    document = SemanticSegmentationService().segment(document)
    document = TableIntelligenceService().enhance(document)
    document = StructureReconstructionService().reconstruct(document)
    document = FinancialSchemaMappingService().map(document)
    return document


def parse_one(
    *,
    sample: dict,
    content: bytes,
    label: str,
    backend_priority: list[str],
    mineru_end_page_id: int | None = None,
) -> dict:
    metadata = DocumentMetadata(
        doc_type="annual_report",
        source="baidu_allpdf_part1",
        filename=sample["filename"],
        extension=".pdf",
        company=sample["company"],
        year=sample["year"],
    )
    parser = PdfDocumentParser(
        backend_priority=backend_priority,
        mineru_start_page_id=0,
        mineru_end_page_id=mineru_end_page_id,
    )
    started = time.perf_counter()
    document = parser.parse(doc_id=f"{sample['doc_id']}-{label}", content=content, metadata=metadata)
    document = run_doc_ai(document)
    elapsed = time.perf_counter() - started
    return summarize(document, elapsed=elapsed, label=label)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    reports: list[dict] = []

    for sample in SAMPLES:
        path = PDF_ROOT / sample["filename"]
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        print("=" * 80)
        print(f"FILE {sample['filename']}")
        print(f"SIZE_MB {path.stat().st_size / 1024 / 1024:.2f}")

        # 1) native full document — text-layer A-share reports usually work here
        native = parse_one(
            sample=sample,
            content=content,
            label="native_full",
            backend_priority=["native_pdf"],
        )
        print(json.dumps(native, ensure_ascii=False, indent=2))
        reports.append({"sample": sample["filename"], **native})

        # 2) mineru first 12 pages — quality probe without full-report runtime
        mineru = parse_one(
            sample=sample,
            content=content,
            label="mineru_first_12",
            backend_priority=["mineru_pdf", "native_pdf"],
            mineru_end_page_id=11,
        )
        print(json.dumps(mineru, ensure_ascii=False, indent=2))
        reports.append({"sample": sample["filename"], **mineru})

    out = ROOT / "data" / "reports" / "annual_report_parse_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()

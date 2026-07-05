import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
from src.claude_copilot.schemas.document import DocumentMetadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-page-id", type=int, default=0)
    parser.add_argument("--end-page-id", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = Path("data/fixtures/jpmc_audited_financial_statements_2024.pdf")
    content = pdf_path.read_bytes()
    parser = PdfDocumentParser(
        backend_priority=["mineru_pdf", "table_pdf", "native_pdf", "ocr_pdf"],
        mineru_start_page_id=args.start_page_id,
        mineru_end_page_id=args.end_page_id,
    )
    metadata = DocumentMetadata(
        doc_type="financial_statement",
        source="official",
        filename=pdf_path.name,
        extension=".pdf",
    )
    started_at = time.perf_counter()
    result = parser.parse(doc_id="real-pdf-test", content=content, metadata=metadata)
    elapsed_seconds = round(time.perf_counter() - started_at, 2)
    block_distribution: dict[str, int] = {}
    for block in result.page_blocks:
        block_distribution[block.block_type] = block_distribution.get(block.block_type, 0) + 1

    failed_pages = sorted({issue.page for issue in result.issues if issue.page is not None})

    print("mineru_page_range=", {"start_page_id": args.start_page_id, "end_page_id": args.end_page_id})
    print("elapsed_seconds=", elapsed_seconds)
    print("parse_route=", result.metadata.parse_route)
    print("parse_backend=", result.metadata.parse_backend)
    print("page_count=", result.metadata.page_count)
    print("parsed_page_range=", result.metadata.parsed_page_range)
    print("parsed_page_count=", result.metadata.parsed_page_count)
    print("quality=", result.quality.model_dump() if result.quality else None)
    print("issues=", [issue.model_dump() for issue in result.issues[:10]])
    print("failed_pages=", failed_pages)
    print("sections=", len(result.sections))
    print("page_blocks=", len(result.page_blocks))
    print("tables=", len(result.tables))
    print("block_distribution=", dict(sorted(block_distribution.items())))
    print("table_titles=", [table.title for table in result.tables[:5]])
    print("raw_text_preview=", result.raw_text[:1200].replace("\n", " "))


if __name__ == "__main__":
    main()

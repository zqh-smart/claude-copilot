from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.parser.pdf_parser import PdfDocumentParser
from app.pipeline.feature_pipeline.schema_mapping.service import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation.service import SemanticSegmentationService
from app.pipeline.feature_pipeline.table_intelligence.service import TableIntelligenceService
from app.pipeline.feature_pipeline.structure_reconstruction.service import StructureReconstructionService
from src.claude_copilot.schemas.document import DocumentMetadata


def main() -> None:
    pdf_path = Path("data/fixtures/jpmc_audited_financial_statements_2024.pdf")
    content = pdf_path.read_bytes()
    metadata = DocumentMetadata(
        doc_type="financial_statement",
        source="fixture",
        filename=pdf_path.name,
        extension=".pdf",
        company="JPMorgan Chase & Co.",
        year=2024,
    )
    parser = PdfDocumentParser(
        backend_priority=["mineru_pdf", "table_pdf", "native_pdf", "ocr_pdf"],
        mineru_start_page_id=0,
        mineru_end_page_id=20,
    )
    document = parser.parse(doc_id="inspect-doc-ai", content=content, metadata=metadata)
    document = SemanticSegmentationService().segment(document)
    document = TableIntelligenceService().enhance(document)
    document = StructureReconstructionService().reconstruct(document)
    document = FinancialSchemaMappingService().map(document)

    print("document", {"route": document.metadata.parse_route, "backend": document.metadata.parse_backend})
    print("semantic_sections")
    for section in document.financial_schema.semantic_sections:
        print(
            {
                "section_id": section.section_id,
                "type": section.section_type,
                "title": section.title,
                "page_range": section.page_range,
                "confidence": section.confidence,
            }
        )

    print("tables")
    for table in document.tables:
        print(
            {
                "table_id": table.table_id,
                "table_type": table.table_type,
                "page": table.page,
                "page_range": table.metadata.get("page_range"),
                "title": table.title,
                "source_section": table.source_section,
                "source_section_title": table.metadata.get("source_section_title"),
                "period_headers": table.period_headers,
                "metric_keys": sorted(table.normalized_metrics.keys()),
                "note_number": table.note_number,
                "note_title": table.note_title,
                "note_category": table.note_category,
                "semantic_row_count": len(table.semantic_rows),
            }
        )

    print("statements")
    for statement in document.financial_schema.statements:
        print(
            {
                "table_id": statement.table_id,
                "type": statement.statement_type,
                "title": statement.title,
                "page_range": statement.page_range,
                "period_headers": statement.period_headers,
                "metric_keys": sorted(statement.metrics.keys()),
                "source_section": statement.source_section,
            }
        )

    print("notes")
    for note in document.financial_schema.notes:
        print(
            {
                "table_id": note.table_id,
                "note_number": note.note_number,
                "note_title": note.note_title,
                "note_category": note.note_category,
                "page_range": note.page_range,
                "source_section": note.source_section,
                "fact_count": len(note.note_facts),
                "dimension_headers": note.dimension_headers,
            }
        )


if __name__ == "__main__":
    main()

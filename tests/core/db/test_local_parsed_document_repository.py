from pathlib import Path

from app.core.db.parsed_document_repository import LocalParsedDocumentRepository
from src.claude_copilot.schemas.document import DocumentMetadata, ParsedDocument, ParsedSection, ParsedTable


def test_local_parsed_document_repository_round_trip(tmp_path: Path) -> None:
    repository = LocalParsedDocumentRepository(str(tmp_path))
    document = ParsedDocument(
        doc_id="doc-local-1",
        metadata=DocumentMetadata(doc_type="annual_report", source="test", filename="report.pdf", extension=".pdf"),
        sections=[
            ParsedSection(
                section_id="doc-local-1-section-1",
                title="Overview",
                content="Revenue increased.",
                section_type="section",
            )
        ],
        tables=[
            ParsedTable(
                table_id="doc-local-1-table-1",
                table_type="income_statement",
                title="Statements of income",
                page=1,
                headers=["Metric", "2024"],
                rows=[["Revenue", "100"]],
            )
        ],
    )

    parsed_path = repository.save(document)
    restored = repository.get(document.doc_id)

    assert Path(parsed_path).exists()
    assert restored.doc_id == document.doc_id
    assert restored.sections[0].title == "Overview"
    assert restored.tables[0].table_type == "income_statement"

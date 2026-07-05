from decimal import Decimal
from datetime import datetime

from app.core.db.postgres_mappers import (
    document_record_from_orm,
    document_record_to_orm,
    metric_fact_to_orm,
    note_fact_to_orm,
    split_fact_value,
)
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    DocumentProcessingStatus,
    DocumentRecord,
    FinancialMetricFact,
    FinancialNoteFact,
)


def test_split_fact_value_handles_numeric_and_text_values() -> None:
    assert split_fact_value(12) == (Decimal("12"), None)
    assert split_fact_value(12.5) == (Decimal("12.5"), None)
    assert split_fact_value("N/A") == (None, "N/A")


def test_document_record_mapper_round_trip() -> None:
    record = DocumentRecord(
        doc_id="doc-map-1",
        filename="report.pdf",
        status=DocumentProcessingStatus.COMPLETED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        storage_path="/tmp/report.pdf",
        parsed_path="postgres:parsed_documents/doc-map-1",
        segment_count=2,
        metadata=DocumentMetadata(doc_type="annual_report", source="test", filename="report.pdf", extension=".pdf"),
    )

    orm = document_record_to_orm(record)
    restored = document_record_from_orm(orm)

    assert restored.doc_id == record.doc_id
    assert restored.status == record.status
    assert restored.parsed_path == record.parsed_path


def test_financial_fact_mappers_preserve_numeric_and_provenance() -> None:
    metric_fact = FinancialMetricFact(
        metric_key="revenue",
        period="2024",
        value=100,
        statement_type="income_statement",
        source_table_id="table-1",
        provenance={"source": "test"},
    )
    note_fact = FinancialNoteFact(
        fact_key="ending_balance",
        note_number="Note 1",
        note_title="Allowance",
        note_category="credit_losses",
        row_label="Ending balance",
        row_type="metric",
        dimensions={"Class": "Consumer"},
        period_values={"2024": 88},
        tags=["balance"],
        source_table_id="table-2",
        provenance={"source": "test"},
    )

    metric_orm = metric_fact_to_orm("doc-map-2", metric_fact, 1)
    note_orm = note_fact_to_orm("doc-map-2", note_fact, 1)

    assert metric_orm.value_numeric == Decimal("100")
    assert metric_orm.value_text is None
    assert metric_orm.provenance["source"] == "test"

    assert note_orm.fact_type == "note"
    assert note_orm.dimensions == {"Class": "Consumer"}
    assert note_orm.provenance["period_values"] == {"2024": 88}

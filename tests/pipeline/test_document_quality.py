from app.pipeline.feature_pipeline.cleaning import DocumentCleaningService
from app.pipeline.feature_pipeline.evaluation.document_quality import (
    character_error_rate,
    table_teds,
)
from app.pipeline.feature_pipeline.parser.table_normalization import (
    normalize_currency_columns,
)
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    ParsedDocument,
    ParsedPageBlock,
)


def test_currency_column_normalization_repairs_split_financial_values() -> None:
    headers, rows = normalize_currency_columns(
        ["Metric", "2024", "", "2023"],
        [
            ["Revenue", "$ 100", "$", "90"],
            ["Losses", "", "(10)", "(8)"],
        ],
    )

    assert headers == ["Metric", "2024", "2023"]
    assert rows == [["Revenue", "$ 100", "90"], ["Losses", "(10)", "(8)"]]


def test_currency_column_normalization_compacts_shifted_period_values() -> None:
    headers, rows = normalize_currency_columns(
        ["Metric", "2024", "", "2023", "2022"],
        [
            ["Revenue", "$ 100", "$", "90 $", "80"],
            ["Losses", "", "(10)", "(8)", "(7)"],
            ["Shares", "2.5", "2.4", "2.3", ""],
        ],
    )

    assert headers == ["Metric", "2024", "2023", "2022"]
    assert rows == [
        ["Revenue", "$ 100", "90 $", "80"],
        ["Losses", "(10)", "(8)", "(7)"],
        ["Shares", "2.5", "2.4", "2.3"],
    ]


def test_cer_and_teds_reward_exact_table_and_penalize_structure_error() -> None:
    reference = "<table><tr><th>Metric</th><th>2024</th></tr><tr><td>Revenue</td><td>100</td></tr></table>"
    wrong = "<table><tr><th>Metric</th><th></th><th>2024</th></tr><tr><td>Revenue</td><td>$</td><td>90</td></tr></table>"

    assert character_error_rate("Revenue 100", "Revenue 100") == 0.0
    assert table_teds(reference, reference) == 1.0
    assert table_teds(reference, wrong) < 0.8


def test_cleaning_removes_repeated_english_margins_and_duplicate_long_block() -> None:
    narrative = "Management discussion explains operating performance and liquidity. " * 3
    document = ParsedDocument(
        doc_id="cleaning",
        metadata=DocumentMetadata(doc_type="annual_report", source="test"),
        page_blocks=[
            *[
                ParsedPageBlock(
                    block_id=f"footer-{page}",
                    block_type="paragraph",
                    text=f"ACME 2024 Annual Report | {page}",
                    page=page,
                )
                for page in range(1, 4)
            ],
            ParsedPageBlock(block_id="body-1", block_type="paragraph", text=narrative, page=1),
            ParsedPageBlock(block_id="body-2", block_type="paragraph", text=narrative, page=2),
        ],
    )

    cleaned = DocumentCleaningService().clean(document)

    assert [block.text for block in cleaned.page_blocks] == [narrative]

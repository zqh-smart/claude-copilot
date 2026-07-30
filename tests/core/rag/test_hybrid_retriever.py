from pathlib import Path

from app.core.db import LocalSegmentRepository
from app.core.rag import LocalRetriever
from src.claude_copilot.schemas.document import DocumentSegment


def _build_retriever(tmp_path: Path) -> LocalRetriever:
    repository = LocalSegmentRepository(str(tmp_path))
    repository.replace_for_document(
        "doc-1",
        [
            DocumentSegment(
                segment_id="mda",
                document_id="doc-1",
                position=1,
                content="管理层讨论与分析：公司主营业务经营情况良好，收入持续增长。",
                metadata={"section_type": "management_discussion"},
            ),
            DocumentSegment(
                segment_id="note",
                document_id="doc-1",
                position=2,
                content="附注：会计政策变更说明，对个别科目列报无重大影响。",
                metadata={"section_type": "financial_note"},
            ),
        ],
    )
    return LocalRetriever(repository)


def test_hybrid_retriever_boosts_section_hints(tmp_path: Path) -> None:
    retriever = _build_retriever(tmp_path)

    plain_hits = retriever.retrieve(
        "公司经营情况如何？",
        doc_id="doc-1",
        top_k=1,
    )
    hinted_hits = retriever.retrieve(
        "公司经营情况如何？",
        doc_id="doc-1",
        top_k=1,
        section_hints=["management_discussion"],
    )

    assert plain_hits[0][0].segment_id in {"mda", "note"}
    assert hinted_hits[0][0].segment_id == "mda"


def test_hybrid_retriever_lexical_finds_management_discussion(tmp_path: Path) -> None:
    retriever = _build_retriever(tmp_path)

    hits = retriever.retrieve(
        "管理层如何讨论与分析公司经营情况？",
        doc_id="doc-1",
        top_k=1,
        section_hints=["management_discussion"],
    )

    assert hits[0][0].segment_id == "mda"
    assert hits[0][1] > 0

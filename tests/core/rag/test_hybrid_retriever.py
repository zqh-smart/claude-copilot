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


def test_hybrid_retriever_deduplicates_equivalent_candidate_text(tmp_path: Path) -> None:
    overlapping = "Revenue growth reflected stronger product demand and customer acquisition. " * 3
    repository = LocalSegmentRepository(str(tmp_path))
    repository.replace_for_document(
        "doc-duplicates",
        [
            DocumentSegment(
                segment_id="duplicate-1",
                document_id="doc-duplicates",
                position=1,
                content="Revenue increased because product demand improved.",
            ),
            DocumentSegment(
                segment_id="duplicate-2",
                document_id="doc-duplicates",
                position=2,
                content="Revenue increased because product demand improved.\n",
            ),
            DocumentSegment(
                segment_id="distinct",
                document_id="doc-duplicates",
                position=3,
                content="New customer acquisition also supported revenue growth.",
            ),
            DocumentSegment(
                segment_id="overlap-long",
                document_id="doc-duplicates",
                position=4,
                content=overlapping + "Management expects demand to remain stable.",
            ),
            DocumentSegment(
                segment_id="overlap-contained",
                document_id="doc-duplicates",
                position=5,
                content=overlapping,
            ),
        ],
    )

    hits = LocalRetriever(repository).retrieve(
        "revenue growth",
        doc_id="doc-duplicates",
        top_k=5,
    )

    normalized = ["".join(segment.content.split()).casefold() for segment, _ in hits]
    assert len(normalized) == len(set(normalized))
    assert len(hits) == 3
    long_contents = [item for item in normalized if len(item) >= 120]
    assert not any(
        left in right or right in left
        for index, left in enumerate(long_contents)
        for right in long_contents[index + 1 :]
    )


def test_hybrid_retriever_penalizes_ocf_chunk_for_revenue_question(tmp_path: Path) -> None:
    repository = LocalSegmentRepository(str(tmp_path))
    repository.replace_for_document(
        "doc-metric",
        [
            DocumentSegment(
                segment_id="revenue-mda",
                document_id="doc-metric",
                position=1,
                content="营业收入增长主要系产品需求旺盛与客户拓展。",
                metadata={"section_type": "management_discussion"},
            ),
            DocumentSegment(
                segment_id="ocf-mda",
                document_id="doc-metric",
                position=2,
                content="经营活动产生的现金流量净额同比增长，主要系销售回款改善。",
                metadata={"section_type": "management_discussion"},
            ),
        ],
    )
    retriever = LocalRetriever(repository)

    hits = retriever.retrieve(
        "2021年营业收入相对2020年为什么增长？",
        doc_id="doc-metric",
        top_k=2,
        section_hints=["management_discussion"],
        metric_keys=["revenue"],
    )

    assert hits[0][0].segment_id == "revenue-mda"


def test_hybrid_retriever_penalizes_note_tables_for_risk_question(tmp_path: Path) -> None:
    repository = LocalSegmentRepository(str(tmp_path))
    repository.replace_for_document(
        "doc-risk",
        [
            DocumentSegment(
                segment_id="risk-mda",
                document_id="doc-risk",
                position=1,
                content="市场竞争加剧的风险：同业竞争与产品迭代加快。",
                metadata={"section_type": "risk_section"},
            ),
            DocumentSegment(
                segment_id="note-fair-value",
                document_id="doc-risk",
                position=2,
                content="金融资产公允价值计量及金融负债合同负债余额如下表所示。",
                metadata={"section_type": "financial_note"},
            ),
        ],
    )
    hits = LocalRetriever(repository).retrieve(
        "公司面临哪些市场风险？",
        doc_id="doc-risk",
        top_k=2,
        section_hints=["risk_section"],
    )
    assert hits[0][0].segment_id == "risk-mda"


def test_hybrid_retriever_filters_evidence_free_cross_references() -> None:
    reference = DocumentSegment(
        segment_id="reference",
        document_id="doc",
        position=1,
        content="具体请见本报告第三节管理层讨论与分析之未来发展展望。",
    )
    evidence = DocumentSegment(
        segment_id="evidence",
        document_id="doc",
        position=2,
        content="参见主营业务分析，公司营业收入同比增长34.63%。",
    )

    filtered = LocalRetriever._filter_evidence_free_references(
        [(reference, 0.9), (evidence, 0.8)]
    )

    assert [segment.segment_id for segment, _ in filtered] == ["evidence"]

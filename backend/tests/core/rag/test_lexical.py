from app.core.db.lexical import bm25_lite_score, tokenize


def test_tokenize_handles_chinese_and_english() -> None:
    tokens = tokenize("2021年营业收入 revenue growth")

    assert "2021" in tokens
    assert "revenue" in tokens
    assert "growth" in tokens
    assert any("营业" in token or token == "营业收入" for token in tokens)


def test_bm25_lite_prefers_matching_content() -> None:
    query_tokens = tokenize("管理层讨论与分析 经营情况")
    strong = bm25_lite_score(
        query_tokens,
        "管理层讨论与分析：公司主营业务经营情况良好，收入持续增长。",
    )
    weak = bm25_lite_score(
        query_tokens,
        "附注：会计政策变更说明。",
    )

    assert strong > weak

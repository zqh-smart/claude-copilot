from app.core.rag.graph_rag_gold import expand_graph_rag_cases, load_graph_rag_gold_fixture


def test_graph_rag_gold_expands_to_100_plus_cases() -> None:
    fixture = load_graph_rag_gold_fixture()
    cases = expand_graph_rag_cases(fixture)
    assert len(cases) >= 100
    assert all(case.get("id") and case.get("question") for case in cases)

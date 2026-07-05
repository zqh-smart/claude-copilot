from typing import Callable, TypedDict


class ResearchState(TypedDict, total=False):
    doc_id: str
    company_id: str | None
    question: str
    top_k: int
    hits: list[dict]
    query_analysis: dict
    metrics: list[dict]
    calculations: list[dict]
    graph_paths: list[dict]
    warnings: list[str]
    evidence: list[dict]
    synthesis: dict
    critic: dict
    revision_count: int
    max_revisions: int
    grounded: bool
    answer: str


class _FallbackCompiledGraph:
    def __init__(
        self,
        retrieve_fn: Callable[[dict], dict],
        synthesize_fn: Callable[[dict], dict],
        critic_fn: Callable[[dict], dict],
        revise_fn: Callable[[dict], dict],
    ) -> None:
        self._retrieve_fn = retrieve_fn
        self._synthesize_fn = synthesize_fn
        self._critic_fn = critic_fn
        self._revise_fn = revise_fn

    def invoke(self, state: dict) -> dict:
        updated = {**state, **self._retrieve_fn(state)}
        updated = {**updated, **self._synthesize_fn(updated)}
        updated = {**updated, **self._critic_fn(updated)}
        while self._should_revise(updated):
            updated = {**updated, **self._revise_fn(updated)}
            updated = {**updated, **self._critic_fn(updated)}
        return updated

    def _should_revise(self, state: dict) -> bool:
        return (
            not state.get("critic", {}).get("passed", False)
            and state.get("revision_count", 0) < state.get("max_revisions", 1)
        )


def build_research_graph(
    retrieve_fn: Callable[[dict], dict],
    synthesize_fn: Callable[[dict], dict],
    critic_fn: Callable[[dict], dict],
    revise_fn: Callable[[dict], dict],
):
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return _FallbackCompiledGraph(
            retrieve_fn,
            synthesize_fn,
            critic_fn,
            revise_fn,
        )

    builder = StateGraph(ResearchState)
    builder.add_node("retrieve_context", retrieve_fn)
    builder.add_node("synthesize_answer", synthesize_fn)
    builder.add_node("critique_answer", critic_fn)
    builder.add_node("revise_answer", revise_fn)
    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "synthesize_answer")
    builder.add_edge("synthesize_answer", "critique_answer")
    builder.add_conditional_edges(
        "critique_answer",
        _route_after_critique,
        {"revise": "revise_answer", "end": END},
    )
    builder.add_edge("revise_answer", "critique_answer")
    return builder.compile()


def _route_after_critique(state: ResearchState) -> str:
    if state.get("critic", {}).get("passed", False):
        return "end"
    if state.get("revision_count", 0) >= state.get("max_revisions", 1):
        return "end"
    return "revise"

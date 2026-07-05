class QueryExpansionService:
    """Minimal query expansion placeholder inspired by Bank-style RAG decomposition."""

    def expand(self, question: str, n: int = 3) -> list[str]:
        seeds = [question.strip()]
        if "风险" in question:
            seeds.append(f"{question} 风险因素")
        if "财务" in question or "指标" in question:
            seeds.append(f"{question} 关键财务指标")
        return [item for item in seeds[:n] if item]

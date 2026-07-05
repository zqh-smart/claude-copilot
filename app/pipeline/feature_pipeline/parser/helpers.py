from src.claude_copilot.schemas.document import DocumentMetadata


def with_parse_metadata(
    metadata: DocumentMetadata,
    *,
    parse_backend: str,
    parse_route: str | None = None,
    parse_strategy: str = "dify-style-router",
    page_count: int | None = None,
    parsed_page_range: tuple[int, int] | None = None,
    parsed_page_count: int | None = None,
    content_quality_score: float | None = None,
) -> DocumentMetadata:
    return metadata.model_copy(
        update={
            "parse_backend": parse_backend,
            "parse_route": parse_route,
            "parse_strategy": parse_strategy,
            "page_count": page_count,
            "parsed_page_range": parsed_page_range,
            "parsed_page_count": parsed_page_count,
            "content_quality_score": content_quality_score,
        }
    )

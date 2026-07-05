from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.core.db import PostgresSegmentRepository, get_postgres_session_factory
from app.core.rag import QdrantVectorStore, build_embedding_service


def main() -> int:
    settings = get_settings()
    segment_repo = PostgresSegmentRepository(get_postgres_session_factory())
    embedding_service = build_embedding_service(settings)
    grpc_error: Exception | None = None

    try:
        grpc_client = QdrantClient(
            url=settings.qdrant_url,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=True,
            check_compatibility=False,
            timeout=15,
        )
        grpc_client.collection_exists(settings.qdrant_collection_name)
        qdrant_client = grpc_client
        print("QDRANT_CLIENT grpc")
    except Exception as exc:  # pragma: no cover - environment dependent
        grpc_error = exc
        qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            timeout=15,
            check_compatibility=False,
        )
        qdrant_client.collection_exists(settings.qdrant_collection_name)
        print("QDRANT_CLIENT rest_fallback")
        print(f"QDRANT_GRPC_ERROR {type(grpc_error).__name__}: {grpc_error}")

    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=settings.qdrant_collection_name,
        embedding_service=embedding_service,
    )

    cases = [
        ("95c70ff5b94e4665b466ebe2316d0d90", "docker_smoke", "What does the document say about liquidity risk?"),
        (
            "a7a707b3ef20486a87ff65c8a0a32458",
            "qdrant_smoke",
            "What does the document say about revenue growth and capital ratios?",
        ),
        (
            "3cd602cec2cf4fc481ee08767c607042",
            "silicon_smoke_valid",
            "What does the document say about liquidity risk and credit losses?",
        ),
    ]

    for doc_id, source, query in cases:
        print(f"DOC {doc_id}")
        print(f"SOURCE {source}")
        print(f"QUERY {query}")

        vector_hits = vector_store.search(query, doc_id=doc_id, top_k=3)
        lexical_hits = segment_repo.search(query, doc_id=doc_id, top_k=3)

        print(f"VECTOR_HITS {len(vector_hits)}")
        for idx, (segment, score) in enumerate(vector_hits, start=1):
            snippet = segment.content[:180].replace("\n", " ")
            print(f"VECTOR {idx} {score:.4f} {segment.segment_id} {snippet}")

        print(f"LEXICAL_HITS {len(lexical_hits)}")
        for idx, (segment, score) in enumerate(lexical_hits, start=1):
            snippet = segment.content[:180].replace("\n", " ")
            print(f"LEXICAL {idx} {score:.4f} {segment.segment_id} {snippet}")

        print("---")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

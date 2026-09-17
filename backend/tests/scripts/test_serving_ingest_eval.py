from argparse import Namespace

from scripts import run_serving_ingest_eval


def test_local_protocol_mode_is_isolated_and_not_a_serving_report(monkeypatch) -> None:
    for name in (
        "STORAGE_BACKEND",
        "VECTOR_STORE_BACKEND",
        "GRAPH_STORE_BACKEND",
        "QDRANT_URL",
        "EMBEDDING_BACKEND",
        "RERANK_BACKEND",
        "DOCUMENT_STORAGE_PATH",
        "RAW_DATA_PATH",
        "PARSED_DATA_PATH",
        "GRAPH_DATA_PATH",
    ):
        monkeypatch.setenv(name, "test-original")
    args = Namespace(
        execution_mode="local-protocol",
        storage_backend="postgres",
        vector_backend="qdrant",
        graph_backend="neo4j",
    )

    out_dir, execution_mode = run_serving_ingest_eval._configure_execution(args)

    assert execution_mode == "local-protocol"
    assert out_dir == run_serving_ingest_eval.LOCAL_OUT_DIR
    assert out_dir != run_serving_ingest_eval.OUT_DIR
    assert run_serving_ingest_eval.os.environ["STORAGE_BACKEND"] == "local"
    assert run_serving_ingest_eval.os.environ["VECTOR_STORE_BACKEND"] == "qdrant"
    assert run_serving_ingest_eval.os.environ["GRAPH_STORE_BACKEND"] == "local"
    assert run_serving_ingest_eval.os.environ["QDRANT_URL"] == ":memory:"
    assert run_serving_ingest_eval.os.environ["EMBEDDING_BACKEND"] == "hash"
    assert run_serving_ingest_eval.os.environ["RERANK_BACKEND"] == "deterministic"


def test_production_mode_preserves_explicit_backend_contract(monkeypatch) -> None:
    for name in ("STORAGE_BACKEND", "VECTOR_STORE_BACKEND", "GRAPH_STORE_BACKEND"):
        monkeypatch.setenv(name, "test-original")
    args = Namespace(
        execution_mode="production-serving",
        storage_backend="postgres",
        vector_backend="qdrant",
        graph_backend="neo4j",
    )

    out_dir, execution_mode = run_serving_ingest_eval._configure_execution(args)

    assert execution_mode == "production-serving"
    assert out_dir == run_serving_ingest_eval.OUT_DIR
    assert run_serving_ingest_eval.os.environ["STORAGE_BACKEND"] == "postgres"
    assert run_serving_ingest_eval.os.environ["VECTOR_STORE_BACKEND"] == "qdrant"
    assert run_serving_ingest_eval.os.environ["GRAPH_STORE_BACKEND"] == "neo4j"

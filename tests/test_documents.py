from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_document_service, get_graph_store, get_research_service
from app.api.services.document_service import DocumentService
from app.api.services.research_service import ResearchService
from app.core.db import LocalDocumentRepository, LocalSegmentRepository
from app.core.kg import LocalKnowledgeGraphStore
from app.core.rag import LocalRetriever
from app.core.storage import LocalFileStorage
from app.main import app
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService


def build_test_services(base_dir: Path) -> tuple[DocumentService, ResearchService]:
    graph_store = LocalKnowledgeGraphStore(str(base_dir / "graph"))
    pipeline = DocumentPipelineService(
        document_repository=LocalDocumentRepository(str(base_dir / "parsed")),
        segment_repository=LocalSegmentRepository(str(base_dir / "parsed")),
        storage=LocalFileStorage(),
        document_storage_path=str(base_dir / "documents"),
        raw_data_path=str(base_dir / "raw"),
        parsed_data_path=str(base_dir / "parsed"),
        graph_store=graph_store,
    )
    document_service = DocumentService(pipeline)
    research_service = ResearchService(
        document_pipeline_service=pipeline,
        retriever=LocalRetriever(LocalSegmentRepository(str(base_dir / "parsed"))),
    )
    return document_service, research_service


def test_document_upload_and_research_preview(tmp_path: Path) -> None:
    document_service, research_service = build_test_services(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: document_service
    app.dependency_overrides[get_research_service] = lambda: research_service

    client = TestClient(app)
    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "report.txt",
                b"Revenue grew strongly. Risk factors include liquidity pressure.",
            )
        },
        data={
            "company": "Demo Bank",
            "year": "2025",
            "doc_type": "annual_report",
            "source": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["segment_count"] >= 1

    doc_id = payload["doc_id"]

    detail_response = client.get(f"/api/v1/documents/{doc_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["metadata"]["company"] == "Demo Bank"

    segments_response = client.get(f"/api/v1/documents/{doc_id}/segments")
    assert segments_response.status_code == 200
    assert len(segments_response.json()) >= 1

    graph_response = client.get(f"/api/v1/documents/{doc_id}/knowledge-graph")
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    assert any(node["node_type"] == "company" for node in graph_payload["nodes"])
    assert any(
        relationship["relationship_type"] == "HAS_RISK"
        for relationship in graph_payload["relationships"]
    )

    graph_store = document_service._pipeline_service._graph_store
    app.dependency_overrides[get_graph_store] = lambda: graph_store
    company_id = graph_payload["company_id"]
    company_graph_response = client.get(f"/api/v1/companies/{company_id}/knowledge-graph")
    assert company_graph_response.status_code == 200
    assert company_graph_response.json()["document_ids"] == [doc_id]

    research_response = client.post(
        "/api/v1/research/preview",
        json={"doc_id": doc_id, "question": "这个文档提到了哪些风险？", "top_k": 3},
    )
    assert research_response.status_code == 200
    research_payload = research_response.json()
    assert research_payload["doc_id"] == doc_id
    assert "风险" in research_payload["question"]
    assert len(research_payload["hits"]) >= 1

    app.dependency_overrides.clear()

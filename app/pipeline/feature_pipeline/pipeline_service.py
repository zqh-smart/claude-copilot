from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.db import (
    DocumentRepositoryProtocol,
    LocalParsedDocumentRepository,
    ParsedDocumentRepositoryProtocol,
    SegmentRepositoryProtocol,
)
from app.core.kg import (
    KnowledgeGraphBuilder,
    KnowledgeGraphStoreProtocol,
    NoOpKnowledgeGraphStore,
)
from app.core.rag.vector_store import VectorStoreProtocol
from app.core.storage import LocalFileStorage
from app.pipeline.feature_pipeline.chunking import ChunkingService
from app.pipeline.feature_pipeline.cleaning import DocumentCleaningService
from app.pipeline.feature_pipeline.indexing import IndexingService
from app.pipeline.feature_pipeline.parser import ParserRouter
from app.pipeline.feature_pipeline.schema_mapping import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation import SemanticSegmentationService
from app.pipeline.feature_pipeline.state_machine import ensure_transition
from app.pipeline.feature_pipeline.structure_reconstruction import StructureReconstructionService
from app.pipeline.feature_pipeline.table_intelligence import TableIntelligenceService
from src.claude_copilot.schemas.document import (
    DocumentMetadata,
    DocumentProcessingStatus,
    DocumentRecord,
)


class DocumentPipelineService:
    def __init__(
        self,
        *,
        document_repository: DocumentRepositoryProtocol,
        segment_repository: SegmentRepositoryProtocol,
        storage: LocalFileStorage,
        document_storage_path: str,
        raw_data_path: str,
        parsed_data_path: str,
        parsed_document_repository: ParsedDocumentRepositoryProtocol | None = None,
        vector_store: VectorStoreProtocol | None = None,
        graph_store: KnowledgeGraphStoreProtocol | None = None,
    ) -> None:
        self._document_repository = document_repository
        self._segment_repository = segment_repository
        self._storage = storage
        self._document_storage_path = document_storage_path
        self._raw_data_path = raw_data_path
        self._parsed_data_path = parsed_data_path
        self._parsed_document_repository = (
            parsed_document_repository
            or LocalParsedDocumentRepository(
                parsed_data_path,
                storage,
            )
        )
        self._parser_router = ParserRouter()
        self._cleaning = DocumentCleaningService()
        self._segmentation = SemanticSegmentationService()
        self._table_intelligence = TableIntelligenceService()
        self._structure_reconstruction = StructureReconstructionService()
        self._schema_mapping = FinancialSchemaMappingService()
        self._chunking = ChunkingService()
        self._indexing = IndexingService(segment_repository, vector_store)
        self._graph_builder = KnowledgeGraphBuilder()
        self._graph_store = graph_store or NoOpKnowledgeGraphStore()

    def ingest(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        company: str | None,
        year: int | None,
        doc_type: str,
        source: str,
        industry: str | None = None,
        company_aliases: list[str] | None = None,
    ) -> DocumentRecord:
        doc_id = uuid4().hex
        suffix = Path(filename).suffix.lower()
        stored_filename = f"{doc_id}{suffix}"
        archived = self._storage.save_bytes(self._document_storage_path, stored_filename, content)
        self._storage.save_bytes(self._raw_data_path, stored_filename, content)

        metadata = DocumentMetadata(
            doc_type=doc_type,
            source=source,
            filename=filename,
            extension=suffix,
            content_type=content_type,
            size_bytes=len(content),
            company=company,
            company_aliases=company_aliases or [],
            industry=industry,
            year=year,
        )
        now = datetime.utcnow()
        record = DocumentRecord(
            doc_id=doc_id,
            filename=filename,
            status=DocumentProcessingStatus.WAITING,
            created_at=now,
            updated_at=now,
            storage_path=str(archived),
            metadata=metadata,
        )
        self._document_repository.save(record)

        try:
            record = self._transition(record, DocumentProcessingStatus.PARSING)
            parsed_document = self._parser_router.parse(
                doc_id=doc_id,
                filename=filename,
                content=content,
                metadata=metadata,
            )

            record = self._transition(record, DocumentProcessingStatus.CLEANING)
            parsed_document = self._cleaning.clean(parsed_document)
            parsed_document = self._segmentation.segment(parsed_document)
            parsed_document = self._table_intelligence.enhance(parsed_document)
            parsed_document = self._structure_reconstruction.reconstruct(parsed_document)
            parsed_document = self._schema_mapping.map(parsed_document)

            record = self._transition(record, DocumentProcessingStatus.CHUNKING)
            parsed_document.segments = self._chunking.chunk(parsed_document)

            parsed_path = self._parsed_document_repository.save(parsed_document)
            record = self._transition(
                record,
                DocumentProcessingStatus.INDEXING,
                parsed_path=str(parsed_path),
            )

            segment_count = self._indexing.index(doc_id, parsed_document.segments)
            self._graph_store.replace_document(self._graph_builder.build(parsed_document))
            record = self._transition(
                record,
                DocumentProcessingStatus.COMPLETED,
                parsed_path=str(parsed_path),
                segment_count=segment_count,
            )
        except Exception as exc:
            record = self._document_repository.update_status(
                doc_id,
                DocumentProcessingStatus.FAILED,
                error_message=str(exc),
            )
        return record

    def list_documents(self) -> list[DocumentRecord]:
        return self._document_repository.list()

    def get_document(self, doc_id: str) -> DocumentRecord:
        return self._document_repository.get(doc_id)

    def get_segments(self, doc_id: str):
        return self._segment_repository.list_for_document(doc_id)

    def get_knowledge_graph(self, doc_id: str):
        self._document_repository.get(doc_id)
        return self._graph_store.get_document(doc_id)

    def _transition(
        self,
        record: DocumentRecord,
        target: DocumentProcessingStatus,
        *,
        parsed_path: str | None = None,
        segment_count: int | None = None,
    ) -> DocumentRecord:
        ensure_transition(record.status, target)
        return self._document_repository.update_status(
            record.doc_id,
            target,
            parsed_path=parsed_path,
            segment_count=segment_count,
        )

from src.claude_copilot.schemas.document import DocumentProcessingStatus


ALLOWED_TRANSITIONS: dict[DocumentProcessingStatus, set[DocumentProcessingStatus]] = {
    DocumentProcessingStatus.WAITING: {
        DocumentProcessingStatus.PARSING,
        DocumentProcessingStatus.PAUSED,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.PARSING: {
        DocumentProcessingStatus.CLEANING,
        DocumentProcessingStatus.CHUNKING,
        DocumentProcessingStatus.PAUSED,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.CLEANING: {
        DocumentProcessingStatus.CHUNKING,
        DocumentProcessingStatus.PAUSED,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.CHUNKING: {
        DocumentProcessingStatus.INDEXING,
        DocumentProcessingStatus.PAUSED,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.INDEXING: {
        DocumentProcessingStatus.COMPLETED,
        DocumentProcessingStatus.PAUSED,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.PAUSED: {
        DocumentProcessingStatus.PARSING,
        DocumentProcessingStatus.CLEANING,
        DocumentProcessingStatus.CHUNKING,
        DocumentProcessingStatus.INDEXING,
        DocumentProcessingStatus.FAILED,
    },
    DocumentProcessingStatus.FAILED: {
        DocumentProcessingStatus.WAITING,
        DocumentProcessingStatus.PARSING,
    },
    DocumentProcessingStatus.COMPLETED: set(),
}


def ensure_transition(
    current: DocumentProcessingStatus,
    target: DocumentProcessingStatus,
) -> None:
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid document status transition: {current} -> {target}")

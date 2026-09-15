class ClaudeCopilotError(Exception):
    """Base application error."""


class DocumentNotFoundError(ClaudeCopilotError):
    """Raised when a document cannot be found."""


class IngestionJobNotFoundError(ClaudeCopilotError):
    """Raised when an ingestion job cannot be found."""


class DocumentProcessingCancelledError(ClaudeCopilotError):
    """Raised at a pipeline stage boundary after cooperative cancellation."""


class CompanyNotFoundError(ClaudeCopilotError):
    """Raised when a company cannot be found in structured financial data."""


class UnsupportedDocumentTypeError(ClaudeCopilotError):
    """Raised when no parser is available for the uploaded document."""


class PersistenceBackendError(ClaudeCopilotError):
    """Raised when a configured persistence backend cannot be initialized or used."""

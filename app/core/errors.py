class ClaudeCopilotError(Exception):
    """Base application error."""


class DocumentNotFoundError(ClaudeCopilotError):
    """Raised when a document cannot be found."""


class CompanyNotFoundError(ClaudeCopilotError):
    """Raised when a company cannot be found in structured financial data."""


class UnsupportedDocumentTypeError(ClaudeCopilotError):
    """Raised when no parser is available for the uploaded document."""


class PersistenceBackendError(ClaudeCopilotError):
    """Raised when a configured persistence backend cannot be initialized or used."""

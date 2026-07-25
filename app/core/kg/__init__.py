"""Knowledge graph and structured memory modules.

This package is reserved for later graph-based reasoning and memory features,
inspired first by Bank-copilot-main and later extended for financial entity graphs.
"""

from app.core.kg.builder import KnowledgeGraphBuilder
from app.core.kg.entity_extractor import FinancialEntityRelationExtractor
from app.core.kg.store import (
    KnowledgeGraphStoreProtocol,
    LocalKnowledgeGraphStore,
    Neo4jKnowledgeGraphStore,
    NoOpKnowledgeGraphStore,
)

__all__ = [
    "KnowledgeGraphBuilder",
    "FinancialEntityRelationExtractor",
    "KnowledgeGraphStoreProtocol",
    "LocalKnowledgeGraphStore",
    "Neo4jKnowledgeGraphStore",
    "NoOpKnowledgeGraphStore",
]

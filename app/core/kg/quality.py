"""Deterministic quality gates for document knowledge graphs."""

from __future__ import annotations

from dataclasses import dataclass

from src.claude_copilot.schemas.knowledge_graph import DocumentKnowledgeGraph


@dataclass(frozen=True)
class GraphQualityReport:
    node_count: int
    relationship_count: int
    duplicate_node_id_count: int
    duplicate_relationship_id_count: int
    missing_endpoint_count: int
    wrong_document_id_count: int
    missing_evidence_count: int
    evidence_grounding_rate: float
    passed: bool


def evaluate_document_graph(graph: DocumentKnowledgeGraph) -> GraphQualityReport:
    node_ids = [node.node_id for node in graph.nodes]
    relationship_ids = [item.relationship_id for item in graph.relationships]
    known_nodes = set(node_ids)
    missing_endpoint_count = sum(
        item.source_node_id not in known_nodes or item.target_node_id not in known_nodes
        for item in graph.relationships
    )
    wrong_document_id_count = sum(
        item.document_id != graph.document_id for item in graph.relationships
    )
    missing_evidence_count = sum(
        not (item.evidence_text or item.page_range) for item in graph.relationships
    )
    relationship_count = len(graph.relationships)
    evidence_rate = round(
        (relationship_count - missing_evidence_count) / max(relationship_count, 1),
        4,
    )
    duplicate_node_ids = len(node_ids) - len(set(node_ids))
    duplicate_relationship_ids = len(relationship_ids) - len(set(relationship_ids))
    passed = bool(
        duplicate_node_ids == 0
        and duplicate_relationship_ids == 0
        and missing_endpoint_count == 0
        and wrong_document_id_count == 0
        and missing_evidence_count == 0
    )
    return GraphQualityReport(
        node_count=len(node_ids),
        relationship_count=relationship_count,
        duplicate_node_id_count=duplicate_node_ids,
        duplicate_relationship_id_count=duplicate_relationship_ids,
        missing_endpoint_count=missing_endpoint_count,
        wrong_document_id_count=wrong_document_id_count,
        missing_evidence_count=missing_evidence_count,
        evidence_grounding_rate=evidence_rate,
        passed=passed,
    )

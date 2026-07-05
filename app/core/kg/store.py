from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from src.claude_copilot.schemas.knowledge_graph import (
    DocumentKnowledgeGraph,
    GraphPath,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)


class KnowledgeGraphStoreProtocol(Protocol):
    def replace_document(self, graph: DocumentKnowledgeGraph) -> None: ...

    def get_document(self, document_id: str) -> DocumentKnowledgeGraph: ...

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]: ...


class NoOpKnowledgeGraphStore:
    def replace_document(self, graph: DocumentKnowledgeGraph) -> None:
        return None

    def get_document(self, document_id: str) -> DocumentKnowledgeGraph:
        return DocumentKnowledgeGraph(document_id=document_id)

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]:
        return []


class LocalKnowledgeGraphStore:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def replace_document(self, graph: DocumentKnowledgeGraph) -> None:
        self._path(graph.document_id).write_text(
            graph.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def get_document(self, document_id: str) -> DocumentKnowledgeGraph:
        path = self._path(document_id)
        if not path.exists():
            return DocumentKnowledgeGraph(document_id=document_id)
        return DocumentKnowledgeGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]:
        graphs = (
            [self.get_document(document_id)]
            if document_id
            else [
                DocumentKnowledgeGraph.model_validate_json(path.read_text(encoding="utf-8"))
                for path in self._base_dir.glob("*.json")
            ]
        )
        terms = self._query_terms(query)
        paths: list[GraphPath] = []
        for graph in graphs:
            if company_id and graph.company_id != company_id:
                continue
            node_map = {node.node_id: node for node in graph.nodes}
            for relationship in graph.relationships:
                source = node_map.get(relationship.source_node_id)
                target = node_map.get(relationship.target_node_id)
                if source is None or target is None:
                    continue
                haystack = self._path_text(source, target, relationship)
                matched = sum(term in haystack for term in terms)
                type_bonus = self._type_bonus(query, source, target, relationship)
                if terms and matched == 0 and type_bonus == 0:
                    continue
                score = min(1.0, 0.2 + matched / max(len(terms), 1) * 0.6 + type_bonus)
                paths.append(
                    GraphPath(
                        path_id=relationship.relationship_id,
                        summary=(
                            f"{source.name} -[{relationship.relationship_type}]-> "
                            f"{target.name}"
                        ),
                        score=round(score, 4),
                        nodes=[source, target],
                        relationships=[relationship],
                    )
                )
        return sorted(paths, key=lambda item: (-item.score, item.path_id))[:limit]

    def _path(self, document_id: str) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", document_id)
        return self._base_dir / f"{safe_name}.json"

    @staticmethod
    def _query_terms(query: str) -> set[str]:
        normalized = query.casefold()
        english = set(re.findall(r"[a-z0-9_]{2,}", normalized))
        chinese = set(re.findall(r"[\u4e00-\u9fff]{2,}", normalized))
        return english | chinese

    @staticmethod
    def _path_text(
        source: KnowledgeGraphNode,
        target: KnowledgeGraphNode,
        relationship: KnowledgeGraphRelationship,
    ) -> str:
        return " ".join(
            (
                source.name,
                target.name,
                relationship.relationship_type,
                json.dumps(source.properties, ensure_ascii=False, default=str),
                json.dumps(target.properties, ensure_ascii=False, default=str),
            )
        ).casefold()

    @staticmethod
    def _type_bonus(
        query: str,
        source: KnowledgeGraphNode,
        target: KnowledgeGraphNode,
        relationship: KnowledgeGraphRelationship,
    ) -> float:
        normalized = query.casefold()
        node_types = {source.node_type, target.node_type}
        if ("risk" in normalized or "风险" in normalized) and "risk" in node_types:
            return 0.2
        if (
            any(term in normalized for term in ("metric", "revenue", "指标", "营收", "利润"))
            and "metric" in node_types
        ):
            return 0.2
        if (
            any(term in normalized for term in ("relationship", "related", "关系", "关联"))
            and relationship.relationship_type
        ):
            return 0.15
        return 0.0


class Neo4jKnowledgeGraphStore:
    _LABELS = {
        "company": "Company",
        "document": "Document",
        "metric": "Metric",
        "risk": "Risk",
    }
    _RELATIONSHIPS = {"HAS_DOCUMENT", "REPORTS_METRIC", "HAS_RISK", "EVIDENCED_BY"}

    def __init__(self, *, uri: str, username: str, password: str, database: str) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("Neo4j backend requires the 'neo4j' Python package") from exc
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database
        self._ensure_schema()

    def replace_document(self, graph: DocumentKnowledgeGraph) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(
                "MATCH (n {document_id: $document_id}) DETACH DELETE n",
                document_id=graph.document_id,
            ).consume()
            for node in graph.nodes:
                label = self._LABELS[node.node_type]
                properties = self._neo4j_properties(
                    {
                        "node_id": node.node_id,
                        "name": node.name,
                        "document_id": node.document_id,
                        **node.properties,
                    }
                )
                session.run(
                    f"MERGE (n:{label} {{node_id: $node_id}}) SET n += $properties",
                    node_id=node.node_id,
                    properties=properties,
                ).consume()
            for relationship in graph.relationships:
                relationship_type = relationship.relationship_type
                if relationship_type not in self._RELATIONSHIPS:
                    raise ValueError(f"Unsupported graph relationship: {relationship_type}")
                session.run(
                    (
                        "MATCH (source {node_id: $source_id}), (target {node_id: $target_id}) "
                        f"MERGE (source)-[r:{relationship_type} "
                        "{relationship_id: $relationship_id}]->(target) "
                        "SET r += $properties"
                    ),
                    source_id=relationship.source_node_id,
                    target_id=relationship.target_node_id,
                    relationship_id=relationship.relationship_id,
                    properties=self._neo4j_properties(
                        {
                            "document_id": relationship.document_id,
                            **relationship.properties,
                        }
                    ),
                ).consume()

    def _ensure_schema(self) -> None:
        with self._driver.session(database=self._database) as session:
            for label in self._LABELS.values():
                constraint_name = f"{label.casefold()}_node_id_unique"
                session.run(
                    (
                        f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.node_id IS UNIQUE"
                    )
                ).consume()

    def get_document(self, document_id: str) -> DocumentKnowledgeGraph:
        with self._driver.session(database=self._database) as session:
            records = session.run(
                """
                MATCH (source)-[r {document_id: $document_id}]->(target)
                RETURN source, labels(source) AS source_labels,
                       r, type(r) AS relationship_type,
                       target, labels(target) AS target_labels
                """,
                document_id=document_id,
            )
            return self._records_to_graph(document_id, list(records))

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]:
        graph = self.get_document(document_id) if document_id else None
        if graph is None:
            return []
        local = _InMemoryGraphSearch(graph)
        return local.search(query, company_id=company_id, limit=limit)

    def _records_to_graph(
        self,
        document_id: str,
        records: list[Any],
    ) -> DocumentKnowledgeGraph:
        nodes: dict[str, KnowledgeGraphNode] = {}
        relationships: dict[str, KnowledgeGraphRelationship] = {}
        company_id = None
        for record in records:
            source = self._node_from_record(record["source"], record["source_labels"])
            target = self._node_from_record(record["target"], record["target_labels"])
            nodes[source.node_id] = source
            nodes[target.node_id] = target
            if source.node_type == "company":
                company_id = source.properties.get("company_id")
            relationship_data = dict(record["r"])
            relationship_id = relationship_data.pop("relationship_id")
            relationship_document_id = relationship_data.pop("document_id", document_id)
            relationships[relationship_id] = KnowledgeGraphRelationship(
                relationship_id=relationship_id,
                relationship_type=record["relationship_type"],
                source_node_id=source.node_id,
                target_node_id=target.node_id,
                document_id=relationship_document_id,
                properties=relationship_data,
            )
        return DocumentKnowledgeGraph(
            document_id=document_id,
            company_id=company_id,
            nodes=list(nodes.values()),
            relationships=list(relationships.values()),
        )

    def _node_from_record(self, raw: Any, labels: list[str]) -> KnowledgeGraphNode:
        values = dict(raw)
        reverse_labels = {value: key for key, value in self._LABELS.items()}
        node_type = next(reverse_labels[label] for label in labels if label in reverse_labels)
        node_id = values.pop("node_id")
        name = values.pop("name")
        document_id = values.pop("document_id", None)
        return KnowledgeGraphNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            document_id=document_id,
            properties=values,
        )

    @staticmethod
    def _neo4j_properties(properties: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for key, value in properties.items():
            if value is None:
                continue
            if isinstance(value, (dict, tuple)):
                result[key] = json.dumps(value, ensure_ascii=False, default=str)
            else:
                result[key] = value
        return result


class _InMemoryGraphSearch(LocalKnowledgeGraphStore):
    def __init__(self, graph: DocumentKnowledgeGraph) -> None:
        self._graph = graph

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]:
        if company_id and self._graph.company_id != company_id:
            return []
        node_map = {node.node_id: node for node in self._graph.nodes}
        terms = self._query_terms(query)
        paths = []
        for relationship in self._graph.relationships:
            source = node_map.get(relationship.source_node_id)
            target = node_map.get(relationship.target_node_id)
            if source is None or target is None:
                continue
            haystack = self._path_text(source, target, relationship)
            matched = sum(term in haystack for term in terms)
            bonus = self._type_bonus(query, source, target, relationship)
            if terms and matched == 0 and bonus == 0:
                continue
            paths.append(
                GraphPath(
                    path_id=relationship.relationship_id,
                    summary=f"{source.name} -[{relationship.relationship_type}]-> {target.name}",
                    score=round(
                        min(1.0, 0.2 + matched / max(len(terms), 1) * 0.6 + bonus),
                        4,
                    ),
                    nodes=[source, target],
                    relationships=[relationship],
                )
            )
        return sorted(paths, key=lambda item: (-item.score, item.path_id))[:limit]

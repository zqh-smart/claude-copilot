from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from src.claude_copilot.schemas.knowledge_graph import (
    CompanyKnowledgeGraph,
    DocumentKnowledgeGraph,
    GraphPath,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)


class KnowledgeGraphStoreProtocol(Protocol):
    def replace_document(self, graph: DocumentKnowledgeGraph) -> None: ...

    def get_document(self, document_id: str) -> DocumentKnowledgeGraph: ...

    def get_company(self, company_id: str) -> CompanyKnowledgeGraph: ...

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

    def get_company(self, company_id: str) -> CompanyKnowledgeGraph:
        return CompanyKnowledgeGraph(company_id=company_id)

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

    def get_company(self, company_id: str) -> CompanyKnowledgeGraph:
        graphs = [
            DocumentKnowledgeGraph.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self._base_dir.glob("*.json")
        ]
        return _merge_company_graphs(company_id, [g for g in graphs if g.company_id == company_id])

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
        if company_id and document_id is None:
            merged = self.get_company(company_id)
            graphs = [
                DocumentKnowledgeGraph(
                    document_id=f"company:{company_id}",
                    company_id=company_id,
                    nodes=merged.nodes,
                    relationships=merged.relationships,
                )
            ]
        terms = self._query_terms(query)
        paths: list[GraphPath] = []
        for graph in graphs:
            if company_id and graph.company_id != company_id:
                continue
            node_map = {node.node_id: node for node in graph.nodes}
            paths.extend(
                self._collect_paths(
                    node_map=node_map,
                    relationships=graph.relationships,
                    query=query,
                    terms=terms,
                )
            )
        deduped = {path.path_id: path for path in paths}
        return sorted(deduped.values(), key=lambda item: (-item.score, item.path_id))[:limit]

    @staticmethod
    def _collect_paths(
        *,
        node_map: dict[str, KnowledgeGraphNode],
        relationships: list[KnowledgeGraphRelationship],
        query: str,
        terms: set[str],
    ) -> list[GraphPath]:
        paths: list[GraphPath] = []
        for relationship in relationships:
            path = LocalKnowledgeGraphStore._score_edge(
                node_map=node_map,
                relationship=relationship,
                query=query,
                terms=terms,
            )
            if path is not None:
                paths.append(path)

        outgoing: dict[str, list[KnowledgeGraphRelationship]] = defaultdict(list)
        for relationship in relationships:
            if relationship.source_node_id in node_map and relationship.target_node_id in node_map:
                outgoing[relationship.source_node_id].append(relationship)

        for first in relationships:
            source = node_map.get(first.source_node_id)
            middle = node_map.get(first.target_node_id)
            if source is None or middle is None:
                continue
            for second in outgoing.get(middle.node_id, []):
                if second.source_node_id != middle.node_id:
                    continue
                end = node_map.get(second.target_node_id)
                if end is None or end.node_id == source.node_id:
                    continue
                haystack = " ".join(
                    (
                        LocalKnowledgeGraphStore._path_text(source, middle, first),
                        LocalKnowledgeGraphStore._path_text(middle, end, second),
                    )
                )
                matched = sum(term in haystack for term in terms)
                bonus = max(
                    LocalKnowledgeGraphStore._type_bonus(query, source, middle, first),
                    LocalKnowledgeGraphStore._type_bonus(query, middle, end, second),
                )
                if terms and matched == 0 and bonus == 0:
                    continue
                score = min(1.0, 0.15 + matched / max(len(terms), 1) * 0.5 + bonus)
                paths.append(
                    GraphPath(
                        path_id=f"{first.relationship_id}::{second.relationship_id}",
                        summary=(
                            f"{source.name} -[{first.relationship_type}]-> {middle.name} "
                            f"-[{second.relationship_type}]-> {end.name}"
                        ),
                        score=round(score, 4),
                        nodes=[source, middle, end],
                        relationships=[first, second],
                    )
                )
        return paths

    @staticmethod
    def _score_edge(
        *,
        node_map: dict[str, KnowledgeGraphNode],
        relationship: KnowledgeGraphRelationship,
        query: str,
        terms: set[str],
    ) -> GraphPath | None:
        source = node_map.get(relationship.source_node_id)
        target = node_map.get(relationship.target_node_id)
        if source is None or target is None:
            return None
        haystack = LocalKnowledgeGraphStore._path_text(source, target, relationship)
        matched = sum(term in haystack for term in terms)
        type_bonus = LocalKnowledgeGraphStore._type_bonus(query, source, target, relationship)
        if terms and matched == 0 and type_bonus == 0:
            return None
        score = min(1.0, 0.2 + matched / max(len(terms), 1) * 0.6 + type_bonus)
        return GraphPath(
            path_id=relationship.relationship_id,
            summary=f"{source.name} -[{relationship.relationship_type}]-> {target.name}",
            score=round(score, 4),
            nodes=[source, target],
            relationships=[relationship],
        )

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
            bonus = 0.2
            if relationship.relationship_type == "HAS_RISK":
                bonus += 0.06
            return bonus
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
        if (
            any(term in normalized for term in ("subsidiary", "子公司"))
            and "subsidiary" in node_types
        ):
            return 0.25
        if any(term in normalized for term in ("industry", "行业")) and "industry" in node_types:
            return 0.25
        if (
            any(term in normalized for term in ("segment", "business unit", "业务板块", "分部"))
            and "business_segment" in node_types
        ):
            return 0.25
        if (
            any(term in normalized for term in ("competitor", "competition", "竞争对手", "竞争"))
            and relationship.relationship_type == "COMPETES_WITH"
        ):
            return 0.25
        return 0.0


class Neo4jKnowledgeGraphStore:
    _LABELS = {
        "company": "Company",
        "subsidiary": "Subsidiary",
        "industry": "Industry",
        "business_segment": "BusinessSegment",
        "event": "Event",
        "document": "Document",
        "metric": "Metric",
        "risk": "Risk",
    }
    _RELATIONSHIPS = {
        "HAS_DOCUMENT",
        "REPORTS_METRIC",
        "HAS_RISK",
        "OWNS",
        "OPERATES_IN",
        "AFFECTED_BY",
        "COMPETES_WITH",
        "EVIDENCED_BY",
    }

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
                "MATCH ()-[r {document_id: $document_id}]->() DELETE r",
                document_id=graph.document_id,
            ).consume()
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
                merge_lists = {
                    key: properties.pop(key, []) for key in ("aliases", "years", "document_ids")
                }
                session.run(
                    (
                        f"MERGE (n:{label} {{node_id: $node_id}}) "
                        "SET n += $properties "
                        "SET n.aliases = reduce(a = coalesce(n.aliases, []), x IN $aliases | "
                        "CASE WHEN x IN a THEN a ELSE a + x END), "
                        "n.years = reduce(a = coalesce(n.years, []), x IN $years | "
                        "CASE WHEN x IN a THEN a ELSE a + x END), "
                        "n.document_ids = reduce("
                        "a = coalesce(n.document_ids, []), x IN $document_ids | "
                        "CASE WHEN x IN a THEN a ELSE a + x END)"
                    ),
                    node_id=node.node_id,
                    properties=properties,
                    **merge_lists,
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
                            "page_range": relationship.page_range,
                            "evidence_text": relationship.evidence_text,
                            "confidence": relationship.confidence,
                            **relationship.properties,
                        }
                    ),
                ).consume()
            session.run(
                """
                MATCH (n)
                WHERE NOT (n)--()
                  AND (n:Company OR n:Subsidiary OR n:Industry OR n:BusinessSegment)
                DELETE n
                """
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

    def get_company(self, company_id: str) -> CompanyKnowledgeGraph:
        with self._driver.session(database=self._database) as session:
            document_ids = [
                record["document_id"]
                for record in session.run(
                    """
                    MATCH (c:Company {company_id: $company_id})-[r]->()
                    WHERE r.document_id IS NOT NULL
                    RETURN DISTINCT r.document_id AS document_id
                    """,
                    company_id=company_id,
                )
            ]
        return _merge_company_graphs(
            company_id,
            [self.get_document(document_id) for document_id in document_ids],
        )

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        company_id: str | None = None,
        limit: int = 10,
    ) -> list[GraphPath]:
        graph = (
            self.get_document(document_id)
            if document_id
            else self.get_company(company_id)
            if company_id
            else None
        )
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
            page_range = relationship_data.pop("page_range", None)
            if isinstance(page_range, str):
                page_range = json.loads(page_range)
            evidence_text = relationship_data.pop("evidence_text", None)
            confidence = relationship_data.pop("confidence", 1.0)
            relationships[relationship_id] = KnowledgeGraphRelationship(
                relationship_id=relationship_id,
                relationship_type=record["relationship_type"],
                source_node_id=source.node_id,
                target_node_id=target.node_id,
                document_id=relationship_document_id,
                page_range=tuple(page_range) if page_range else None,
                evidence_text=evidence_text,
                confidence=confidence,
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
    def __init__(self, graph: DocumentKnowledgeGraph | CompanyKnowledgeGraph) -> None:
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
        paths = self._collect_paths(
            node_map=node_map,
            relationships=self._graph.relationships,
            query=query,
            terms=terms,
        )
        return sorted(paths, key=lambda item: (-item.score, item.path_id))[:limit]


def _merge_company_graphs(
    company_id: str,
    graphs: list[DocumentKnowledgeGraph],
) -> CompanyKnowledgeGraph:
    nodes: dict[str, KnowledgeGraphNode] = {}
    relationships: dict[str, KnowledgeGraphRelationship] = {}
    years: set[int] = set()
    company_name = None
    for graph in graphs:
        for node in graph.nodes:
            previous = nodes.get(node.node_id)
            if previous is None:
                nodes[node.node_id] = node
            else:
                properties = dict(previous.properties)
                for key, value in node.properties.items():
                    if key in {"aliases", "years", "document_ids"}:
                        properties[key] = list(dict.fromkeys([*properties.get(key, []), *value]))
                    else:
                        properties[key] = value
                nodes[node.node_id] = previous.model_copy(update={"properties": properties})
            if node.node_type == "company" and node.properties.get("company_id") == company_id:
                company_name = node.name
            years.update(year for year in node.properties.get("years", []) if isinstance(year, int))
        relationships.update((item.relationship_id, item) for item in graph.relationships)
    return CompanyKnowledgeGraph(
        company_id=company_id,
        company_name=company_name,
        document_ids=sorted(graph.document_id for graph in graphs),
        years=sorted(years),
        nodes=list(nodes.values()),
        relationships=list(relationships.values()),
    )

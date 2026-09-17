from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.db.financial_data_repository import extract_period_year
from app.core.kg.entity_extractor import FinancialEntityRelationExtractor
from src.claude_copilot.entity_resolution import EntityResolver
from src.claude_copilot.schemas.document import ParsedDocument
from src.claude_copilot.schemas.knowledge_graph import (
    DocumentKnowledgeGraph,
    KnowledgeGraphNode,
    KnowledgeGraphRelationship,
)


class KnowledgeGraphBuilder:
    _RISK_LABELS: dict[str, tuple[str, ...]] = {
        "liquidity_risk": ("liquidity", "流动性"),
        "credit_risk": ("credit risk", "credit loss", "信用风险", "信贷风险"),
        "market_risk": ("market risk", "volatility", "市场风险", "市场波动"),
        "operational_risk": ("operational risk", "操作风险", "运营风险"),
        "regulatory_risk": ("regulatory", "regulation", "监管风险", "合规风险"),
        "cybersecurity_risk": ("cyber", "information security", "网络安全", "信息安全"),
        "interest_rate_risk": ("interest rate risk", "利率风险"),
        "currency_risk": ("foreign exchange risk", "currency risk", "汇率风险"),
        "supply_chain_risk": ("supply chain", "供应链风险"),
    }

    def __init__(
        self,
        resolver: EntityResolver | None = None,
        extractor: FinancialEntityRelationExtractor | None = None,
    ) -> None:
        self._resolver = resolver or EntityResolver()
        self._extractor = extractor or FinancialEntityRelationExtractor(self._resolver)

    def build(self, document: ParsedDocument) -> DocumentKnowledgeGraph:
        company_name = (
            document.financial_schema.company
            if document.financial_schema and document.financial_schema.company
            else document.metadata.company
        )
        resolved_company = (
            self._resolver.resolve_company(
                company_name,
                aliases=document.metadata.company_aliases,
            )
            if company_name
            else None
        )
        company_id = resolved_company.entity_id if resolved_company else None
        nodes: dict[str, KnowledgeGraphNode] = {}
        relationships: dict[str, KnowledgeGraphRelationship] = {}

        document_node_id = f"document:{document.doc_id}"
        nodes[document_node_id] = KnowledgeGraphNode(
            node_id=document_node_id,
            node_type="document",
            name=document.metadata.filename or document.doc_id,
            document_id=document.doc_id,
            properties={
                "doc_type": document.metadata.doc_type,
                "source": document.metadata.source,
                "year": document.metadata.year,
            },
        )

        company_node_id = None
        if company_id and company_name:
            company_node_id = f"company:{company_id}"
            nodes[company_node_id] = KnowledgeGraphNode(
                node_id=company_node_id,
                node_type="company",
                name=resolved_company.canonical_name,
                properties={
                    "company_id": company_id,
                    "canonical_key": resolved_company.canonical_key,
                    "aliases": list(resolved_company.aliases),
                    "years": [document.metadata.year] if document.metadata.year else [],
                    "document_ids": [document.doc_id],
                },
            )
            self._add_relationship(
                relationships,
                "HAS_DOCUMENT",
                company_node_id,
                document_node_id,
                document.doc_id,
                page_range=(
                    document.metadata.parsed_page_range
                    or ((1, document.metadata.page_count) if document.metadata.page_count else None)
                ),
                evidence_text=document.metadata.filename or document.doc_id,
                confidence=1.0,
            )

        section_ids = self._add_sections(
            document,
            nodes=nodes,
            relationships=relationships,
            document_node_id=document_node_id,
        )

        if document.financial_schema is not None:
            for fact in document.financial_schema.metric_facts:
                metric_id = self._stable_id(
                    "metric",
                    document.doc_id,
                    fact.metric_key,
                    fact.period,
                    fact.source_table_id or "",
                )
                nodes[metric_id] = KnowledgeGraphNode(
                    node_id=metric_id,
                    node_type="metric",
                    name=fact.metric_key,
                    document_id=document.doc_id,
                    properties={
                        "metric_key": fact.metric_key,
                        "period": fact.period,
                        "period_year": extract_period_year(fact.period),
                        "value": fact.value,
                        "statement_type": fact.statement_type,
                        "unit": fact.unit,
                        "currency": fact.currency,
                        "page_range": fact.page_range,
                        "source_table_id": fact.source_table_id,
                    },
                )
                if company_node_id:
                    self._add_relationship(
                        relationships,
                        "REPORTS_METRIC",
                        company_node_id,
                        metric_id,
                        document.doc_id,
                        page_range=fact.page_range,
                        evidence_text=(f"{fact.metric_key} ({fact.period}) = {fact.value}"),
                        confidence=0.98,
                        properties={
                            "period_year": extract_period_year(fact.period),
                        },
                    )
                self._add_relationship(
                    relationships,
                    "EVIDENCED_BY",
                    metric_id,
                    document_node_id,
                    document.doc_id,
                    page_range=fact.page_range,
                    evidence_text=(f"{fact.metric_key} ({fact.period}) = {fact.value}"),
                    confidence=1.0,
                )
                section_id = self._match_section_id(section_ids, fact.source_section)
                if section_id:
                    self._add_relationship(
                        relationships,
                        "EVIDENCED_BY",
                        metric_id,
                        section_id,
                        document.doc_id,
                        page_range=fact.page_range,
                        evidence_text=(f"{fact.metric_key} ({fact.period}) = {fact.value}"),
                        confidence=0.9,
                    )

        for risk_key, evidence, page_range in self._extract_risks(document):
            risk_id = self._stable_id("risk", document.doc_id, risk_key, evidence[:240])
            nodes[risk_id] = KnowledgeGraphNode(
                node_id=risk_id,
                node_type="risk",
                name=risk_key,
                document_id=document.doc_id,
                properties={
                    "risk_type": risk_key,
                    "evidence": evidence[:1800],
                    "page_range": page_range,
                },
            )
            if company_node_id:
                self._add_relationship(
                    relationships,
                    "HAS_RISK",
                    company_node_id,
                    risk_id,
                    document.doc_id,
                    page_range=page_range,
                    evidence_text=evidence,
                    confidence=0.86,
                )
                self._add_relationship(
                    relationships,
                    "AFFECTED_BY",
                    company_node_id,
                    risk_id,
                    document.doc_id,
                    page_range=page_range,
                    evidence_text=evidence,
                    confidence=0.82,
                )
            self._add_relationship(
                relationships,
                "EVIDENCED_BY",
                risk_id,
                document_node_id,
                document.doc_id,
                page_range=page_range,
                evidence_text=evidence,
                confidence=1.0,
            )
            risk_section_id = section_ids.get("risk_section")
            if risk_section_id:
                self._add_relationship(
                    relationships,
                    "EVIDENCED_BY",
                    risk_id,
                    risk_section_id,
                    document.doc_id,
                    page_range=page_range,
                    evidence_text=evidence,
                    confidence=0.9,
                )

        if company_node_id and company_id:
            for entity in self._extractor.extract(document, company_id=company_id):
                nodes[entity.node_id] = KnowledgeGraphNode(
                    node_id=entity.node_id,
                    node_type=entity.node_type,
                    name=entity.name,
                    document_id=(document.doc_id if entity.node_type in {"event"} else None),
                    properties={
                        **entity.properties,
                        "years": [document.metadata.year] if document.metadata.year else [],
                        "document_ids": [document.doc_id],
                    },
                )
                self._add_relationship(
                    relationships,
                    entity.relationship_type,
                    company_node_id,
                    entity.node_id,
                    document.doc_id,
                    page_range=entity.page_range,
                    evidence_text=entity.evidence_text,
                    confidence=entity.confidence,
                )
                self._add_relationship(
                    relationships,
                    "EVIDENCED_BY",
                    entity.node_id,
                    document_node_id,
                    document.doc_id,
                    page_range=entity.page_range,
                    evidence_text=entity.evidence_text,
                    confidence=1.0,
                )

        return DocumentKnowledgeGraph(
            document_id=document.doc_id,
            company_id=company_id,
            nodes=list(nodes.values()),
            relationships=list(relationships.values()),
        )

    def _add_sections(
        self,
        document: ParsedDocument,
        *,
        nodes: dict[str, KnowledgeGraphNode],
        relationships: dict[str, KnowledgeGraphRelationship],
        document_node_id: str,
    ) -> dict[str, str]:
        ids_by_type: dict[str, str] = {}
        type_counts: dict[str, int] = {}
        for section_type, title, section_id, page_range, body in self._typed_section_sources(
            document
        ):
            node_id = self._stable_id(
                "section",
                document.doc_id,
                section_type,
                title or section_id or "",
            )
            evidence = title or (body[:200] if body else None)
            properties: dict[str, Any] = {
                "section_type": section_type,
                "page_range": page_range,
                "year": document.metadata.year,
            }
            if title:
                properties["title"] = title
            nodes[node_id] = KnowledgeGraphNode(
                node_id=node_id,
                node_type="section",
                name=title or section_type,
                document_id=document.doc_id,
                properties=properties,
            )
            self._add_relationship(
                relationships,
                "HAS_SECTION",
                document_node_id,
                node_id,
                document.doc_id,
                page_range=page_range,
                evidence_text=evidence,
                confidence=1.0,
            )
            self._add_relationship(
                relationships,
                "EVIDENCED_BY",
                node_id,
                document_node_id,
                document.doc_id,
                page_range=page_range,
                evidence_text=evidence,
                confidence=1.0,
            )
            ids_by_type[section_type] = node_id
            type_counts[section_type] = type_counts.get(section_type, 0) + 1
        return {key: value for key, value in ids_by_type.items() if type_counts[key] == 1}

    @staticmethod
    def _typed_section_sources(
        document: ParsedDocument,
    ) -> list[tuple[str, str | None, str | None, tuple[int, int] | None, str | None]]:
        schema = document.financial_schema
        if schema is not None and schema.semantic_sections:
            return [
                (
                    section.section_type,
                    section.title,
                    section.section_id,
                    section.page_range,
                    section.evidence_text,
                )
                for section in schema.semantic_sections
                if section.section_type
            ]
        sources: list[tuple[str, str | None, str | None, tuple[int, int] | None, str | None]] = []
        for section in document.sections:
            if not section.section_type:
                continue
            page_range = (
                (section.page_start, section.page_end or section.page_start)
                if section.page_start is not None
                else None
            )
            sources.append(
                (
                    section.section_type,
                    section.title,
                    section.section_id,
                    page_range,
                    section.content,
                )
            )
        return sources

    @staticmethod
    def _match_section_id(
        section_ids: dict[str, str],
        source_section: str | None,
    ) -> str | None:
        if not source_section:
            return None
        if source_section in section_ids:
            return section_ids[source_section]
        folded = source_section.casefold()
        for section_type, node_id in section_ids.items():
            if section_type.casefold() == folded:
                return node_id
        return None

    def _extract_risks(
        self,
        document: ParsedDocument,
    ) -> list[tuple[str, str, tuple[int, int] | None]]:
        candidates: list[tuple[str, tuple[int, int] | None]] = []
        if document.financial_schema is not None:
            for section in document.financial_schema.semantic_sections:
                text = " ".join(
                    part for part in (section.title, section.evidence_text) if part
                ).strip()
                if text and (
                    section.section_type == "risk_section"
                    or "risk" in text.casefold()
                    or "风险" in text
                ):
                    candidates.append((text, section.page_range))
        if not candidates:
            for section in document.sections:
                text = " ".join(part for part in (section.title, section.content) if part).strip()
                if "risk" in text.casefold() or "风险" in text:
                    page_range = (
                        (section.page_start, section.page_end or section.page_start)
                        if section.page_start is not None
                        else None
                    )
                    candidates.append((text, page_range))

        risks: list[tuple[str, str, tuple[int, int] | None]] = []
        seen: set[tuple[str, str]] = set()
        for text, page_range in candidates:
            normalized = re.sub(r"\s+", " ", text).strip()
            matched = [
                risk_key
                for risk_key, terms in self._RISK_LABELS.items()
                if any(term in normalized.casefold() for term in terms)
            ] or ["general_risk"]
            for risk_key in matched:
                fingerprint = (risk_key, normalized[:240])
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    risks.append((risk_key, normalized, page_range))
        return risks

    def _add_relationship(
        self,
        target: dict[str, KnowledgeGraphRelationship],
        relationship_type: str,
        source_node_id: str,
        target_node_id: str,
        document_id: str,
        *,
        page_range: tuple[int, int] | None = None,
        evidence_text: str | None = None,
        confidence: float = 1.0,
        properties: dict[str, Any] | None = None,
    ) -> None:
        relationship_id = self._stable_id(
            "relationship",
            relationship_type,
            source_node_id,
            target_node_id,
            document_id,
        )
        payload = {key: value for key, value in (properties or {}).items() if value is not None}
        target[relationship_id] = KnowledgeGraphRelationship(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            document_id=document_id,
            page_range=page_range,
            evidence_text=evidence_text[:1800] if evidence_text else None,
            confidence=confidence,
            properties=payload,
        )

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}:{digest}"

from __future__ import annotations

import hashlib
import re

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
    ) -> None:
        relationship_id = self._stable_id(
            "relationship",
            relationship_type,
            source_node_id,
            target_node_id,
            document_id,
        )
        target[relationship_id] = KnowledgeGraphRelationship(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            document_id=document_id,
            page_range=page_range,
            evidence_text=evidence_text[:1800] if evidence_text else None,
            confidence=confidence,
        )

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}:{digest}"

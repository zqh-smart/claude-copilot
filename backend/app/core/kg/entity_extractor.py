from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.claude_copilot.entity_resolution import EntityResolver
from src.claude_copilot.schemas.document import ParsedDocument
from src.claude_copilot.schemas.knowledge_graph import GraphNodeType, GraphRelationshipType


@dataclass(frozen=True)
class ExtractedEntity:
    node_id: str
    node_type: GraphNodeType
    name: str
    relationship_type: GraphRelationshipType
    evidence_text: str
    page_range: tuple[int, int] | None
    confidence: float
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Context:
    text: str
    page_range: tuple[int, int] | None


class FinancialEntityRelationExtractor:
    _INDUSTRIES = {
        "banking": ("banking", "bank", "lending", "deposits", "financial services"),
        "technology": ("software", "cloud computing", "semiconductor", "technology"),
        "automotive": ("automotive", "vehicles", "automobile", "汽车"),
        "healthcare": ("healthcare", "pharmaceutical", "medical device", "医疗"),
        "energy": ("oil and gas", "renewable energy", "energy", "能源"),
        "retail": ("retail stores", "e-commerce", "consumer retail", "零售"),
        "manufacturing": ("manufacturing", "industrial products", "制造"),
    }
    _EVENT_TERMS = {
        "acquisition": ("acquired", "acquisition", "收购", "并购"),
        "merger": ("merged", "merger", "合并"),
        "reorganization": ("reorganized", "reorganization", "重组"),
        "divestiture": ("divested", "divestiture", "出售"),
        "management_change": ("appointed", "resigned", "任命", "辞任"),
        "regulatory_action": ("regulatory action", "penalty", "处罚", "监管措施"),
    }
    _SUBSIDIARY_PATTERNS = (
        re.compile(
            r"(?P<name>[A-Z][A-Za-z0-9&.'’ -]{2,80})\s+"
            r"(?:is|was)\s+(?:a\s+)?(?:wholly[- ]owned\s+|majority[- ]owned\s+)?subsidiary",
            re.I,
        ),
        re.compile(
            r"(?P<name>[\u3400-\u9fffA-Za-z0-9（）()·&. -]{2,60})"
            r"(?:为|是)(?:本|该)?公司(?:的)?(?:全资|控股)?子公司"
        ),
    )
    _COMPETITOR_PATTERNS = (
        re.compile(r"(?:competes? with|competitors? include)\s+(?P<names>[^.;]{2,220})", re.I),
        re.compile(r"(?:主要)?竞争对手(?:包括|为|有|：|:)\s*(?P<names>[^。；]{2,160})"),
    )
    _SEGMENT_PATTERNS = (
        re.compile(
            r"(?:has|had|comprises?|consists? of)\s+(?:\w+\s+)?"
            r"(?:reportable\s+)?business segments?\s*[-:–—]\s*(?P<names>[^.]{5,300})",
            re.I,
        ),
        re.compile(r"(?:业务|经营|报告)分部(?:包括|为|有|：|:)\s*(?P<names>[^。]{3,200})"),
    )

    def __init__(self, resolver: EntityResolver | None = None) -> None:
        self._resolver = resolver or EntityResolver()

    def extract(self, document: ParsedDocument, *, company_id: str) -> list[ExtractedEntity]:
        contexts = self._contexts(document)
        entities: dict[tuple[str, str, str], ExtractedEntity] = {}
        self._extract_industry(document, contexts, company_id, entities)
        self._extract_segments(document, contexts, company_id, entities)
        self._extract_named_relationships(contexts, company_id, entities)
        self._extract_events(contexts, company_id, document.doc_id, entities)
        return list(entities.values())

    def _extract_industry(self, document, contexts, company_id, target) -> None:
        if document.metadata.industry:
            name, evidence, confidence = document.metadata.industry, "upload metadata", 1.0
            page_range = None
        else:
            text = " ".join(context.text for context in contexts).casefold()
            scores = {
                industry: sum(text.count(term) for term in terms)
                for industry, terms in self._INDUSTRIES.items()
            }
            name, score = max(scores.items(), key=lambda item: item[1], default=("", 0))
            if score < 2:
                return
            evidence_context = next(
                context
                for context in contexts
                if any(term in context.text.casefold() for term in self._INDUSTRIES[name])
            )
            evidence = evidence_context.text[:600]
            page_range = evidence_context.page_range
            confidence = min(0.9, 0.62 + score * 0.02)
        node_id = self._resolver.stable_entity_id("industry", name)
        self._put(
            target,
            ExtractedEntity(
                node_id,
                "industry",
                name,
                "OPERATES_IN",
                evidence,
                page_range,
                confidence,
                {"industry_key": name.casefold(), "owner_company_id": company_id},
            ),
        )

    def _extract_segments(self, document, contexts, company_id, target) -> None:
        for context in contexts:
            for pattern in self._SEGMENT_PATTERNS:
                for match in pattern.finditer(context.text):
                    raw = re.split(
                        r"\bwith the remaining\b|，其余",
                        match.group("names"),
                        maxsplit=1,
                    )[0]
                    for name in self._split_names(raw):
                        self._add_owned_entity(
                            target,
                            "business_segment",
                            "OPERATES_IN",
                            name,
                            company_id,
                            match.group(0),
                            context.page_range,
                            0.9,
                        )
        for table in document.tables:
            title = " ".join(part for part in (table.title, table.note_title) if part)
            if "segment" not in title.casefold() and "分部" not in title:
                continue
            for header in table.headers[1:]:
                name = self._clean_name(str(header))
                if self._valid_name(name) and not re.search(
                    r"\b(19|20)\d{2}\b|total|corporate", name, re.I
                ):
                    self._add_owned_entity(
                        target,
                        "business_segment",
                        "OPERATES_IN",
                        name,
                        company_id,
                        title or "segment table header",
                        (table.page, table.page) if table.page else None,
                        0.96,
                    )

    def _extract_named_relationships(self, contexts, company_id, target) -> None:
        for context in contexts:
            for pattern in self._SUBSIDIARY_PATTERNS:
                for match in pattern.finditer(context.text):
                    self._add_owned_entity(
                        target,
                        "subsidiary",
                        "OWNS",
                        match.group("name"),
                        company_id,
                        match.group(0),
                        context.page_range,
                        0.91,
                    )
            for pattern in self._COMPETITOR_PATTERNS:
                for match in pattern.finditer(context.text):
                    for name in self._split_names(match.group("names")):
                        resolved = self._resolver.resolve_company(name)
                        self._put(
                            target,
                            ExtractedEntity(
                                f"company:{resolved.entity_id}",
                                "company",
                                resolved.canonical_name,
                                "COMPETES_WITH",
                                match.group(0),
                                context.page_range,
                                0.86,
                                {
                                    "company_id": resolved.entity_id,
                                    "canonical_key": resolved.canonical_key,
                                    "aliases": list(resolved.aliases),
                                },
                            ),
                        )

    def _extract_events(self, contexts, company_id, document_id, target) -> None:
        count = 0
        for context in contexts:
            for sentence in re.split(r"(?<=[.!?。！？])\s+", context.text):
                normalized = sentence.casefold()
                event_type = next(
                    (
                        key
                        for key, terms in self._EVENT_TERMS.items()
                        if any(term in normalized for term in terms)
                    ),
                    None,
                )
                if not event_type or len(sentence) < 20 or len(sentence) > 700:
                    continue
                node_id = self._resolver.stable_entity_id(
                    "event", f"{event_type}:{sentence[:240]}", owner_id=document_id
                )
                self._put(
                    target,
                    ExtractedEntity(
                        node_id,
                        "event",
                        f"{event_type}: {sentence[:120]}",
                        "AFFECTED_BY",
                        sentence,
                        context.page_range,
                        0.82,
                        {"event_type": event_type, "owner_company_id": company_id},
                    ),
                )
                count += 1
                if count >= 25:
                    return

    def _add_owned_entity(
        self,
        target,
        node_type,
        relationship_type,
        name,
        company_id,
        evidence,
        page_range,
        confidence,
    ) -> None:
        name = self._clean_name(name)
        if not self._valid_name(name):
            return
        node_id = self._resolver.stable_entity_id(node_type, name, owner_id=company_id)
        self._put(
            target,
            ExtractedEntity(
                node_id,
                node_type,
                name,
                relationship_type,
                evidence,
                page_range,
                confidence,
                {
                    "canonical_key": self._resolver.canonical_key(name),
                    "owner_company_id": company_id,
                },
            ),
        )

    @staticmethod
    def _contexts(document: ParsedDocument) -> list[_Context]:
        contexts = []
        for section in document.sections:
            text = re.sub(
                r"\s+", " ", " ".join(filter(None, (section.title, section.content)))
            ).strip()
            page_range = (
                (section.page_start, section.page_end or section.page_start)
                if section.page_start is not None
                else None
            )
            if text:
                contexts.append(_Context(text, page_range))
        return contexts or [_Context(document.raw_text, None)]

    @classmethod
    def _split_names(cls, value: str) -> list[str]:
        value = re.sub(r"\s+(?:and|以及|及|与)\s+", ",", value, flags=re.I)
        return [
            cls._clean_name(item)
            for item in re.split(r"[,;、，；]", value)
            if cls._valid_name(cls._clean_name(item))
        ]

    @staticmethod
    def _clean_name(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" \t\r\n,;:–—-.")

    @staticmethod
    def _valid_name(value: str) -> bool:
        return 2 <= len(value) <= 100 and not value.casefold().startswith(
            ("the company", "the firm", "公司", "group")
        )

    @staticmethod
    def _put(target, entity: ExtractedEntity) -> None:
        key = (entity.node_type, entity.node_id, entity.relationship_type)
        previous = target.get(key)
        if previous is None or entity.confidence > previous.confidence:
            target[key] = entity

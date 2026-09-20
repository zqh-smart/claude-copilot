"""Create, edit, and assist template-bound report drafts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from app.api.services.report_template_catalog import get_report_template, list_report_templates
from app.api.services.workflow_api_service import WorkflowApiService
from app.core.config import get_settings
from app.core.llm import GroundedResearchEngine
from app.core.rag.orchestrator import RetrievalOrchestrator
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from src.claude_copilot.schemas.report_studio import (
    AssistReportDraftResponse,
    CreateReportDraftRequest,
    PatchReportDraftRequest,
    ReportCitation,
    ReportDraft,
    ReportDraftSection,
    ReportDraftSource,
    ReportDraftSummary,
    ReportTemplate,
)
from src.claude_copilot.schemas.research import QueryAnalysis
from src.claude_copilot.schemas.workflows import ReportOutlineRequest


def _now() -> datetime:
    return datetime.now(UTC)


_LEGACY_TEMPLATE_IDS = {
    "investment": "comprehensive_financial",
    "risk": "financial_risk",
}


def _normalize_draft_payload(payload: dict) -> dict:
    normalized = dict(payload)
    template_id = str(normalized.get("template_id") or "comprehensive_financial")
    normalized["template_id"] = _LEGACY_TEMPLATE_IDS.get(template_id, template_id)
    return normalized


def _bullet_text(section: dict) -> list[str]:
    bullets = section.get("bullets")
    if isinstance(bullets, list) and bullets:
        return [str(item).strip() for item in bullets if str(item).strip()]
    for key in ("content", "summary"):
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _section_title(section: dict) -> str:
    return str(section.get("title") or section.get("heading") or "")


def _match_chapter(title: str, hints: list[str]) -> bool:
    if not title or not hints:
        return False
    return any(hint in title for hint in hints)


def _path_label(*, filename: str, section_title: str | None, page: int | None) -> str:
    parts = [filename]
    if section_title:
        parts.append(section_title)
    if page is not None:
        parts.append(f"p.{page}")
    return " · ".join(parts)


def _draft_to_markdown(draft: ReportDraft) -> str:
    parts: list[str] = [f"# {draft.title}", ""]
    citation_by_id = {item.citation_id: item for item in draft.citations}
    for section in draft.sections:
        parts.append(f"## {section.title}")
        parts.append(section.content.strip() or "（本章暂无足够材料，待补充。）")
        used = [citation_by_id[cid] for cid in section.citation_ids if cid in citation_by_id]
        if used:
            parts.append("")
            parts.append("引用路径：")
            for item in used:
                parts.append(f"- [{item.citation_id}] {item.path_label}")
        parts.append("")
    if draft.warnings:
        parts.append("## 局限与说明")
        parts.extend(f"- {item}" for item in draft.warnings[:12])
    return "\n".join(parts).strip()


class ReportDraftStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, draft_id: str) -> Path:
        return self._root / f"{draft_id}.json"

    def save(self, draft: ReportDraft) -> None:
        self._path(draft.draft_id).write_text(
            draft.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def get(self, draft_id: str) -> ReportDraft:
        path = self._path(draft_id)
        if not path.exists():
            raise FileNotFoundError(draft_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReportDraft.model_validate(_normalize_draft_payload(payload))

    def list_summaries(self) -> list[ReportDraftSummary]:
        items: list[ReportDraftSummary] = []
        for path in sorted(
            self._root.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            payload = _normalize_draft_payload(json.loads(path.read_text(encoding="utf-8")))
            items.append(
                ReportDraftSummary(
                    draft_id=payload["draft_id"],
                    title=payload.get("title") or "未命名报告",
                    template_id=payload["template_id"],
                    status=payload.get("status") or "draft",
                    source_count=len(payload.get("sources") or []),
                    updated_at=payload.get("updated_at") or _now(),
                )
            )
        return items


def _hit_page(metadata: dict) -> int | None:
    raw = metadata.get("page") or metadata.get("page_number")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _hit_section_title(metadata: dict) -> str:
    return str(
        metadata.get("section_title")
        or metadata.get("section_type")
        or metadata.get("title")
        or ""
    )


class ReportDraftService:
    def __init__(
        self,
        *,
        workflow_service: WorkflowApiService,
        document_pipeline_service: DocumentPipelineService,
        store: ReportDraftStore | None = None,
        orchestrator: RetrievalOrchestrator | None = None,
        grounded_engine: GroundedResearchEngine | None = None,
    ) -> None:
        self._workflow_service = workflow_service
        self._documents = document_pipeline_service
        self._orchestrator = orchestrator
        self._grounded_engine = grounded_engine
        settings = get_settings()
        self._store = store or ReportDraftStore(Path(settings.report_data_path) / "studio_drafts")

    def list_templates(self) -> list[ReportTemplate]:
        return list_report_templates()

    def list_drafts(self) -> list[ReportDraftSummary]:
        return self._store.list_summaries()

    def get_draft(self, draft_id: str) -> ReportDraft:
        return self._store.get(draft_id)

    def create_draft(self, request: CreateReportDraftRequest) -> ReportDraft:
        template = get_report_template(request.template_id)
        sources: list[ReportDraftSource] = []
        outlines: list[tuple[ReportDraftSource, list[dict], list[dict], list[dict], list[str]]] = []
        question = self._compose_question(template, request)
        metric_keys = list(
            dict.fromkeys(key for chapter in template.chapters for key in chapter.required_metrics)
        )
        section_hints = list(
            dict.fromkeys(hint for chapter in template.chapters for hint in chapter.section_hints)
        )
        for doc_id in request.doc_ids:
            record = self._documents.get_document(doc_id)
            source = ReportDraftSource(
                doc_id=record.doc_id,
                filename=record.filename,
                company=record.metadata.company,
                year=record.metadata.year,
                doc_type=record.metadata.doc_type,
            )
            sources.append(source)
            outline = self._workflow_service.report_outline(
                ReportOutlineRequest(
                    doc_id=doc_id,
                    question=question,
                    top_k=request.top_k,
                    use_workflow=True,
                )
            )
            hits = list(outline.hits or [])
            extra_hits, metrics = self._retrieve_bundle(
                question,
                doc_id,
                request.top_k,
                metric_keys=metric_keys,
                section_hints=section_hints,
            )
            if extra_hits:
                hits.extend(extra_hits)
            outlines.append(
                (
                    source,
                    list(outline.sections or []),
                    hits,
                    metrics,
                    list(outline.warnings or []),
                )
            )

        citations, sections = self._assemble_template(template, outlines, request.length)
        title = request.title or self._default_title(template, sources)
        now = _now()
        warnings = [
            f"{source.filename}: {warning}"
            for source, _, _, _, source_warnings in outlines
            for warning in source_warnings
            if warning and "提纲 MVP" not in warning
        ]
        draft = ReportDraft(
            draft_id=str(uuid4()),
            title=title,
            template_id=template.template_id,
            language=request.language,
            length=request.length,
            prompt=request.prompt,
            status="draft",
            sources=sources,
            sections=sections,
            citations=citations,
            warnings=warnings,
            created_at=now,
            updated_at=now,
        )
        self._store.save(draft)
        return draft

    def patch_draft(self, draft_id: str, request: PatchReportDraftRequest) -> ReportDraft:
        draft = self._store.get(draft_id)
        updates: dict = {"updated_at": _now()}
        if request.title is not None:
            updates["title"] = request.title
        if request.status is not None:
            updates["status"] = request.status
        if request.sections is not None:
            updates["sections"] = request.sections
            updates["status"] = request.status or "revised"
        draft = draft.model_copy(update=updates)
        self._store.save(draft)
        return draft

    def assist(
        self,
        draft_id: str,
        *,
        section_id: str,
        instruction: str,
        apply: bool,
    ) -> AssistReportDraftResponse:
        draft = self._store.get(draft_id)
        section = next((item for item in draft.sections if item.section_id == section_id), None)
        if section is None:
            raise KeyError(section_id)
        suggested = self._suggest_revision(draft, section, instruction)
        suggested = self._keep_citation_markers(section, suggested)
        applied = False
        if apply:
            updated_sections = [
                item.model_copy(update={"content": suggested, "editor_json": None})
                if item.section_id == section_id
                else item
                for item in draft.sections
            ]
            draft = draft.model_copy(
                update={"sections": updated_sections, "status": "revised", "updated_at": _now()}
            )
            self._store.save(draft)
            applied = True
        return AssistReportDraftResponse(
            section_id=section_id,
            suggested_content=suggested,
            applied=applied,
            draft=draft if applied else None,
        )

    def draft_markdown(self, draft: ReportDraft) -> str:
        return _draft_to_markdown(draft)

    def _compose_question(self, template: ReportTemplate, request: CreateReportDraftRequest) -> str:
        extra = request.prompt.strip()
        base = f"按「{template.name}」模版，仅依据指定文档生成报告初稿。"
        if extra:
            return f"{base} 重点：{extra}"
        return base

    def _default_title(
        self,
        template: ReportTemplate,
        sources: list[ReportDraftSource],
    ) -> str:
        company = next((item.company for item in sources if item.company), None)
        years = sorted({item.year for item in sources if item.year is not None})
        year_label = (
            f"{years[0]}-{years[-1]}"
            if len(years) > 1
            else (str(years[0]) if years else "")
        )
        bits = [part for part in (company, year_label, template.name) if part]
        return " ".join(bits) or template.name

    def _retrieve_bundle(
        self,
        question: str,
        doc_id: str,
        top_k: int,
        *,
        metric_keys: list[str],
        section_hints: list[str],
    ) -> tuple[list[dict], list[dict]]:
        if self._orchestrator is None:
            return [], []
        routes: list[str] = ["vector"]
        if metric_keys:
            routes.append("sql")
        result = self._orchestrator.retrieve(
            question,
            doc_id=doc_id,
            company_id=None,
            top_k=top_k,
            analysis_override=QueryAnalysis(
                intent="hybrid" if metric_keys else "semantic",
                routes=routes,  # type: ignore[arg-type]
                metric_keys=metric_keys,
                needs_growth=True,
                section_hints=section_hints,
            ),
        )
        hits = [
            {
                "segment_id": segment.segment_id,
                "content": segment.content,
                "metadata": dict(segment.metadata or {}),
            }
            for segment, _score in result.vector_hits
        ]
        metrics = [item.model_dump(mode="json") for item in result.metrics]
        return hits, metrics

    def _assemble_template(
        self,
        template: ReportTemplate,
        outlines: list[tuple[ReportDraftSource, list[dict], list[dict], list[dict], list[str]]],
        length: str,
    ) -> tuple[list[ReportCitation], list[ReportDraftSection]]:
        citations: list[ReportCitation] = []
        unused_by_source: list[tuple[ReportDraftSource, str, list[str], int | None]] = []
        metric_rows: list[tuple[ReportDraftSource, dict]] = []
        for source, sections, hits, metrics, _warnings in outlines:
            for section in sections:
                unused_by_source.append(
                    (source, _section_title(section), _bullet_text(section), None)
                )
            for hit in hits:
                metadata = dict(hit.get("metadata") or {})
                excerpt = str(hit.get("content") or "").strip()
                if not excerpt:
                    continue
                unused_by_source.append(
                    (
                        source,
                        (
                            f"{_hit_section_title(metadata)} "
                            f"{metadata.get('section_type') or ''}"
                        ).strip(),
                        [excerpt[:280]],
                        _hit_page(metadata),
                    )
                )
            metric_rows.extend((source, item) for item in metrics)

        draft_sections: list[ReportDraftSection] = []
        for chapter in template.chapters:
            match_keys = [*chapter.hints, *chapter.section_hints]
            collected: list[tuple[ReportDraftSource, str, str, int | None, str | None]] = []
            for source, title, bullets, page in unused_by_source:
                if _match_chapter(title, match_keys):
                    for bullet in bullets:
                        collected.append((source, title, bullet, page, None))
            for source, metric in metric_rows:
                key = str(metric.get("metric_key") or "")
                if key and key in chapter.required_metrics:
                    period = metric.get("period") or metric.get("period_year") or "—"
                    value = metric.get("value")
                    collected.append(
                        (source, key, f"{key}（{period}）：{value}", None, key)
                    )
            if not collected and not chapter.must_cite:
                for source, title, bullets, page in unused_by_source[:3]:
                    for bullet in bullets[:1]:
                        collected.append((source, title, bullet, page, None))

            citation_ids: list[str] = []
            lines: list[str] = []
            for source, title, bullet, page, metric_key in collected[: self._bullet_limit(length)]:
                citation = self._add_citation(
                    citations, source, title, bullet, page, metric_key=metric_key
                )
                citation_ids.append(citation.citation_id)
                lines.append(f"{bullet} [{citation.citation_id}]")

            blocks: list[str] = []
            if chapter.analysis_requirements:
                blocks.append("分析要求：")
                blocks.extend(f"- {rule}" for rule in chapter.analysis_requirements)
            if chapter.required_metrics:
                blocks.append("必需指标：" + "、".join(chapter.required_metrics))
            if lines:
                blocks.append("证据：")
                blocks.extend(f"- {line}" for line in lines)
            elif chapter.must_cite:
                blocks.append("（指定材料中尚未检索到足够证据，请补充文档或在调整页改写。）")
            draft_sections.append(
                ReportDraftSection(
                    section_id=f"sec-{chapter.chapter_id}",
                    chapter_id=chapter.chapter_id,
                    title=chapter.title,
                    content="\n".join(blocks),
                    citation_ids=list(dict.fromkeys(citation_ids)),
                    required_metrics=list(chapter.required_metrics),
                    analysis_requirements=list(chapter.analysis_requirements),
                )
            )
        return citations, draft_sections

    @staticmethod
    def _bullet_limit(length: str) -> int:
        if length == "brief":
            return 4
        if length == "long":
            return 12
        return 8

    def _add_citation(
        self,
        citations: list[ReportCitation],
        source: ReportDraftSource,
        title: str,
        excerpt: str,
        page: int | None = None,
        metric_key: str | None = None,
    ) -> ReportCitation:
        citation_id = f"C{len(citations) + 1}"
        item = ReportCitation(
            citation_id=citation_id,
            doc_id=source.doc_id,
            filename=source.filename,
            section_title=title or None,
            page=page,
            excerpt=excerpt[:280],
            path_label=_path_label(
                filename=source.filename,
                section_title=title or None,
                page=page,
            ),
            metric_key=metric_key,
        )
        citations.append(item)
        return item

    def _suggest_revision(
        self,
        draft: ReportDraft,
        section: ReportDraftSection,
        instruction: str,
    ) -> str:
        llm_draft = self._suggest_with_llm(draft, section, instruction)
        if llm_draft:
            return llm_draft
        text = section.content.strip()
        citations = [item for item in draft.citations if item.citation_id in section.citation_ids]
        lowered = instruction.casefold()
        if any(token in lowered for token in ("精简", "缩短", "brief")):
            lines = [line for line in text.splitlines() if line.strip()][:3]
            if lines:
                return "\n".join(lines)
        if any(token in lowered for token in ("补充", "展开", "expand")):
            extras = [
                f"- {item.excerpt} [{item.citation_id}]"
                for item in citations
                if item.excerpt and item.excerpt not in text
            ]
            if extras:
                return f"{text}\n" + "\n".join(extras[:3]) if text else "\n".join(extras[:3])
        if citations and "[C" not in text:
            suffix = " ".join(f"[{item.citation_id}]" for item in citations[:3])
            return f"{text}\n\n依据：{suffix}".strip()
        return text or "（本章仍缺少可引用证据。）"

    def _suggest_with_llm(
        self,
        draft: ReportDraft,
        section: ReportDraftSection,
        instruction: str,
    ) -> str | None:
        if self._grounded_engine is None:
            return None
        citations = [item for item in draft.citations if item.citation_id in section.citation_ids]
        evidence = [
            {
                "evidence_id": item.citation_id,
                "source_type": "vector",
                "content": item.excerpt or item.path_label,
                "path_label": item.path_label,
            }
            for item in citations
        ]
        if not evidence:
            return None
        try:
            synthesis = self._grounded_engine.synthesize(
                question=(
                    f"改写报告章节「{section.title}」。指令：{instruction}。"
                    "只输出该章正文，保留已有 [C数字] 引用，不得虚构数字。"
                    f"\n当前稿：\n{section.content}"
                ),
                evidence=evidence,
            )
        except Exception:
            return None
        return synthesis.answer.strip() or None

    @staticmethod
    def _keep_citation_markers(section: ReportDraftSection, suggested: str) -> str:
        missing = [cid for cid in section.citation_ids if f"[{cid}]" not in suggested]
        if not missing:
            return suggested
        return f"{suggested.rstrip()}\n\n依据：{' '.join(f'[{cid}]' for cid in missing)}"


@lru_cache
def get_report_draft_service() -> ReportDraftService:
    from app.api.dependencies import (
        get_document_pipeline_service,
        get_grounded_research_engine,
        get_research_service,
    )
    from app.api.services.workflow_api_service import get_workflow_api_service

    research = get_research_service()
    return ReportDraftService(
        workflow_service=get_workflow_api_service(),
        document_pipeline_service=get_document_pipeline_service(),
        orchestrator=research.orchestrator,
        grounded_engine=get_grounded_research_engine(),
    )

"""Compose multiple report outlines into one evidence-linked formal report."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.claude_copilot.schemas.workflows import ReportOutlineResponse

_OUTLINE_DISCLAIMER_MARKERS = ("提纲 MVP", "非正式投研报告")


@dataclass(frozen=True)
class ReportSource:
    doc_id: str
    outline: ReportOutlineResponse


@dataclass(frozen=True)
class ComposedReport:
    markdown: str
    warnings: list[str]


@dataclass
class _Evidence:
    text: str
    source_indexes: list[int]

    @property
    def marker(self) -> str:
        return "".join(f"[D{index}]" for index in self.source_indexes)


def _sections_from_markdown(markdown: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "bullets": []}
            sections.append(current)
        elif line.startswith(("- ", "* ")):
            if current is None:
                current = {"title": "报告要点", "bullets": []}
                sections.append(current)
            bullets = current["bullets"]
            assert isinstance(bullets, list)
            bullets.append(line[2:].strip())
        elif line.startswith("# ") and not sections:
            current = {"title": line[2:].strip(), "bullets": []}
            sections.append(current)
    return sections


def _category(title: str) -> str:
    normalized = re.sub(r"^\d+[.、)]\s*", "", title)
    if any(word in normalized for word in ("风险", "不确定", "敞口")):
        return "risk"
    if any(word in normalized for word in ("增长", "趋势", "同比", "复合")):
        return "trend"
    if any(word in normalized for word in ("财务", "指标", "盈利", "现金", "资产")):
        return "financial"
    if any(word in normalized for word in ("局限", "说明", "警告", "限制")):
        return "limitation"
    if any(word in normalized for word in ("公司", "文档", "来源")):
        return "metadata"
    return "other"


def _is_substantive(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not any(
        marker in stripped for marker in _OUTLINE_DISCLAIMER_MARKERS
    )


def _collect_evidence(sources: list[ReportSource]) -> dict[str, list[_Evidence]]:
    buckets: dict[str, dict[str, _Evidence]] = {
        "financial": {},
        "trend": {},
        "risk": {},
        "other": {},
    }
    for source_index, source in enumerate(sources, start=1):
        sections = source.outline.sections or _sections_from_markdown(
            source.outline.answer_markdown
        )
        for section in sections:
            category = _category(str(section.get("title") or ""))
            if category not in buckets:
                continue
            for raw_bullet in section.get("bullets") or []:
                text = str(raw_bullet).strip()
                if not _is_substantive(text):
                    continue
                normalized = re.sub(r"\s+", " ", text).casefold()
                evidence = buckets[category].get(normalized)
                if evidence is None:
                    buckets[category][normalized] = _Evidence(text, [source_index])
                elif source_index not in evidence.source_indexes:
                    evidence.source_indexes.append(source_index)
    return {name: list(items.values()) for name, items in buckets.items()}


def _append_section(parts: list[str], title: str, evidence: list[_Evidence]) -> None:
    parts.extend((f"# {title}", ""))
    if evidence:
        parts.extend(f"- {item.marker} {item.text}" for item in evidence)
    else:
        parts.append("- 未检索到足够的结构化证据，需补充材料后复核。")
    parts.append("")


def compose_formal_report(
    *, report_type: str, question: str, sources: list[ReportSource]
) -> ComposedReport:
    """Build a deduplicated investment or risk report with source markers."""
    if not sources:
        raise ValueError("At least one report source is required")

    evidence = _collect_evidence(sources)
    financial = [*evidence["financial"], *evidence["trend"], *evidence["other"]]
    risks = evidence["risk"]
    summary = ([*risks, *financial] if report_type == "risk" else [*financial, *risks])[:5]

    parts: list[str] = ["# 执行摘要", ""]
    if summary:
        parts.extend(f"- {item.marker} {item.text}" for item in summary)
    else:
        parts.append("- 当前材料不足以形成可验证结论。")
    parts.append("")

    if report_type == "risk":
        _append_section(parts, "核心风险结论", risks)
        _append_section(parts, "财务暴露与缓释依据", financial)
    else:
        _append_section(parts, "核心财务与趋势", financial)
        _append_section(parts, "主要风险", risks)

    parts.extend(("# 数据来源与方法", ""))
    for index, source in enumerate(sources, start=1):
        parts.append(f"- [D{index}] 文档 ID：{source.doc_id}")
    parts.extend(
        (
            f"- 分析问题：{question}",
            "- 方法：基于各文档结构化财务指标、趋势计算和风险证据进行跨来源去重汇总。",
            "",
            "# 局限与合规声明",
            "",
            "- 本报告由自动化系统生成，仅基于已入库材料，不构成投资、法律或审计意见。",
            "- 所有结论均应结合原始文档及最新公开信息进行人工复核。",
        )
    )

    warnings = [
        f"{source.doc_id}: {warning}"
        for source in sources
        for warning in source.outline.warnings
        if _is_substantive(warning)
    ]
    return ComposedReport(markdown="\n".join(parts).strip(), warnings=warnings)

"""Run one full annual-report PDF through DocumentPipelineService and report stage metrics."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import (
    LocalDocumentRepository,
    LocalParsedDocumentRepository,
    LocalSegmentRepository,
)
from app.core.kg import LocalKnowledgeGraphStore
from app.core.rag.embeddings import HashEmbeddingService
from app.core.rag.vector_store import NoOpVectorStore
from app.core.storage import LocalFileStorage
from app.pipeline.feature_pipeline.chunking import ChunkingService
from app.pipeline.feature_pipeline.indexing import IndexingService
from app.pipeline.feature_pipeline.parser import ParserRouter
from app.pipeline.feature_pipeline.pipeline_service import DocumentPipelineService
from app.pipeline.feature_pipeline.schema_mapping import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation import SemanticSegmentationService
from app.pipeline.feature_pipeline.structure_reconstruction import StructureReconstructionService
from app.pipeline.feature_pipeline.table_intelligence import TableIntelligenceService
from src.claude_copilot.schemas.document import DocumentMetadata, DocumentProcessingStatus

PDF_PATH = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
    r"/2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf"
)

OUT_DIR = ROOT / "data" / "reports" / "full_pipeline_eval"


def _stage_timer():
    marks: list[tuple[str, float]] = []

    def mark(name: str) -> None:
        marks.append((name, time.perf_counter()))

    def summary() -> list[dict]:
        rows = []
        for index in range(1, len(marks)):
            name = marks[index][0]
            elapsed = marks[index][1] - marks[index - 1][1]
            rows.append({"stage": name, "elapsed_seconds": round(elapsed, 3)})
        return rows

    return mark, summary


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not PDF_PATH.exists():
        raise FileNotFoundError(PDF_PATH)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_root = OUT_DIR / "run_workspace"
    run_root.mkdir(parents=True, exist_ok=True)

    storage = LocalFileStorage()
    document_repo = LocalDocumentRepository(str(run_root / "docs"))
    segment_repo = LocalSegmentRepository(str(run_root / "segments"))
    parsed_repo = LocalParsedDocumentRepository(str(run_root / "parsed"), storage)
    graph_store = LocalKnowledgeGraphStore(str(run_root / "graph"))

    service = DocumentPipelineService(
        document_repository=document_repo,
        segment_repository=segment_repo,
        storage=storage,
        document_storage_path=str(run_root / "documents"),
        raw_data_path=str(run_root / "raw"),
        parsed_data_path=str(run_root / "parsed"),
        parsed_document_repository=parsed_repo,
        vector_store=NoOpVectorStore(),
        graph_store=graph_store,
    )
    # Keep indexing path active but avoid external Qdrant dependency for this eval.
    service._indexing = IndexingService(segment_repo, NoOpVectorStore())

    content = PDF_PATH.read_bytes()
    mark, timing_summary = _stage_timer()
    mark("start")

    # Instrument internal stages by replaying the same sequence with the same services.
    # Then call ingest for the authoritative end-state (status / persisted artifacts).
    from uuid import uuid4

    doc_id = uuid4().hex
    metadata = DocumentMetadata(
        doc_type="annual_report",
        source="full_pipeline_eval",
        filename=PDF_PATH.name,
        extension=".pdf",
        size_bytes=len(content),
        company="北京指南针科技发展股份有限公司",
        year=2021,
        industry="金融信息服务",
    )

    parsed = ParserRouter().parse(
        doc_id=doc_id,
        filename=PDF_PATH.name,
        content=content,
        metadata=metadata,
    )
    mark("parse")
    parse_snapshot = {
        "route": parsed.metadata.parse_route,
        "backend": parsed.metadata.parse_backend,
        "page_count": parsed.metadata.page_count,
        "quality": parsed.quality.model_dump() if parsed.quality else None,
        "raw_text_chars": len(parsed.raw_text or ""),
        "page_blocks": len(parsed.page_blocks),
        "block_types": dict(Counter(block.block_type for block in parsed.page_blocks)),
        "tables": len(parsed.tables),
        "sections": len(parsed.sections),
        "issues": [issue.model_dump() for issue in parsed.issues[:10]],
    }

    parsed = SemanticSegmentationService().segment(parsed)
    mark("segmentation")
    semantic_sections = [
        section
        for section in parsed.sections
        if section.metadata.get("source") == "semantic_segmentation"
    ]
    segmentation_snapshot = {
        "semantic_section_count": len(semantic_sections),
        "semantic_types": dict(Counter(section.section_type for section in semantic_sections)),
        "sample_titles": [
            {
                "type": section.section_type,
                "title": section.title,
                "page_start": section.page_start,
                "page_end": section.page_end,
            }
            for section in semantic_sections[:12]
        ],
    }

    parsed = TableIntelligenceService().enhance(parsed)
    mark("table_intelligence")
    table_snapshot = {
        "tables": len(parsed.tables),
        "table_types": dict(Counter(table.table_type or "unknown" for table in parsed.tables)),
        "with_period_headers": sum(1 for table in parsed.tables if table.period_headers),
        "with_normalized_metrics": sum(1 for table in parsed.tables if table.normalized_metrics),
        "sample_statements": [
            {
                "type": table.table_type,
                "title": table.title,
                "page": table.page,
                "period_headers": table.period_headers,
                "metric_keys": sorted(table.normalized_metrics.keys())[:10],
            }
            for table in parsed.tables
            if table.table_type in {"balance_sheet", "income_statement", "cash_flow", "equity"}
        ][:12],
    }

    parsed = StructureReconstructionService().reconstruct(parsed)
    mark("structure_reconstruction")
    structure_snapshot = {
        "sections_after": len(parsed.sections),
        "page_blocks": len(parsed.page_blocks),
    }

    parsed = FinancialSchemaMappingService().map(parsed)
    mark("schema_mapping")
    schema = parsed.financial_schema
    schema_snapshot = {
        "has_schema": schema is not None,
        "statement_count": len(schema.statements) if schema else 0,
        "note_count": len(schema.notes) if schema else 0,
        "metric_fact_count": len(schema.metric_facts) if schema else 0,
        "note_fact_count": len(schema.note_facts) if schema else 0,
        "metrics_index_size": len(schema.metrics_index) if schema else 0,
        "metrics_index_keys": sorted((schema.metrics_index or {}).keys()) if schema else [],
        "statements": [
            {
                "type": statement.statement_type,
                "title": statement.title,
                "periods": statement.period_headers,
                "metrics": sorted(statement.metrics.keys()),
                "page_range": statement.page_range,
            }
            for statement in (schema.statements if schema else [])
        ][:20],
    }

    segments = ChunkingService().chunk(parsed)
    mark("chunking")
    chunk_snapshot = {
        "segment_count": len(segments),
        "content_types": dict(
            Counter(segment.metadata.get("content_type", "unknown") for segment in segments)
        ),
        "avg_chars": round(sum(len(segment.content) for segment in segments) / max(len(segments), 1), 1),
        "samples": [
            {
                "segment_id": segment.segment_id,
                "chars": len(segment.content),
                "content_type": segment.metadata.get("content_type"),
                "preview": segment.content[:160].replace("\n", " "),
            }
            for segment in segments[:5]
        ],
    }

    record = service.ingest(
        filename=PDF_PATH.name,
        content_type="application/pdf",
        content=content,
        company="北京指南针科技发展股份有限公司",
        year=2021,
        doc_type="annual_report",
        source="full_pipeline_eval",
        industry="金融信息服务",
        company_aliases=["指南针", "300803"],
    )
    mark("ingest_persist_index_graph")

    graph = service.get_knowledge_graph(record.doc_id) if record.status == DocumentProcessingStatus.COMPLETED else None
    graph_snapshot = None
    if graph is not None:
        graph_snapshot = {
            "node_count": len(getattr(graph, "nodes", []) or []),
            "edge_count": len(getattr(graph, "relationships", []) or getattr(graph, "edges", []) or []),
            "node_types": dict(
                Counter(getattr(node, "node_type", getattr(node, "type", "unknown")) for node in (graph.nodes or []))
            ),
        }

    # Cleaning stage note: status exists in state machine but is not invoked by ingest today.
    cleaning_status = {
        "state_machine_has_cleaning": True,
        "pipeline_invokes_cleaning": False,
        "note": "CLEANING is defined in state_machine but DocumentPipelineService currently skips it (PARSING -> CHUNKING).",
    }

    report = {
        "document": {
            "filename": PDF_PATH.name,
            "size_mb": round(PDF_PATH.stat().st_size / 1024 / 1024, 2),
            "doc_id_instrumented": doc_id,
            "doc_id_ingested": record.doc_id,
            "final_status": record.status.value if hasattr(record.status, "value") else str(record.status),
            "error_message": record.error_message,
            "segment_count_record": record.segment_count,
            "parsed_path": record.parsed_path,
        },
        "stage_timings": timing_summary(),
        "cleaning_stage": cleaning_status,
        "stages": {
            "parse": parse_snapshot,
            "segmentation": segmentation_snapshot,
            "table_intelligence": table_snapshot,
            "structure_reconstruction": structure_snapshot,
            "schema_mapping": schema_snapshot,
            "chunking": chunk_snapshot,
            "knowledge_graph": graph_snapshot,
        },
        "optimization_assessment": {
            "parse": "部分完成：文本层年报可走 table_pdf；复杂版式/扫描件仍需 MinerU；表格噪声偏多。",
            "cleaning": "缺失：状态机有 CLEANING，但流水线未实现页眉页脚/目录/重复块清洗。",
            "segmentation": "可用但偏碎：中文章节已识别，相邻同类型可再合并。",
            "table_intelligence": "可用但需打磨：三大报表能识别，期间脏值与附注误判仍在。",
            "structure_reconstruction": "弱：目前贡献有限，需结合清洗后的块再评估。",
            "schema_mapping": "半完成：有 statements/metrics，但部分资产负债表 metrics 为空。",
            "chunking": "基础可用：固定窗口切分，尚未做 parent-child / 章节感知切分。",
            "indexing": "本次用 NoOpVectorStore 验证通路；生产需接 Qdrant + 真实 embedding。",
            "knowledge_graph": "MVP：能建图，实体/关系抽取仍偏规则。",
        },
    }

    out_path = OUT_DIR / "指南针_2021_full_pipeline_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-readable markdown summary
    md_lines = [
        "# 完整文档流水线评测：指南针 2021 年报",
        "",
        f"- 文件：`{PDF_PATH.name}`",
        f"- 大小：{report['document']['size_mb']} MB",
        f"- 最终状态：`{report['document']['final_status']}`",
        f"- ingest doc_id：`{report['document']['doc_id_ingested']}`",
        "",
        "## 阶段耗时",
        "",
    ]
    for row in report["stage_timings"]:
        md_lines.append(f"- **{row['stage']}**: {row['elapsed_seconds']}s")
    md_lines.extend(
        [
            "",
            "## 各阶段结果摘要",
            "",
            f"- Parse：route=`{parse_snapshot['route']}`, tables={parse_snapshot['tables']}, blocks={parse_snapshot['page_blocks']}",
            f"- Segmentation：semantic_sections={segmentation_snapshot['semantic_section_count']}, types={segmentation_snapshot['semantic_types']}",
            f"- Table intelligence：typed={table_snapshot['table_types']}",
            f"- Schema：statements={schema_snapshot['statement_count']}, metric_facts={schema_snapshot['metric_fact_count']}, metrics_index={schema_snapshot['metrics_index_keys']}",
            f"- Chunking：segments={chunk_snapshot['segment_count']}, types={chunk_snapshot['content_types']}",
            f"- Graph：{graph_snapshot}",
            "",
            "## 清洗阶段",
            "",
            cleaning_status["note"],
            "",
            "## 是否还需要优化",
            "",
        ]
    )
    for stage, note in report["optimization_assessment"].items():
        md_lines.append(f"- **{stage}**: {note}")

    md_path = OUT_DIR / "指南针_2021_full_pipeline_report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"WROTE {out_path}")
    print(f"WROTE {md_path}")


if __name__ == "__main__":
    main()

"""Stage-wise evaluation scorecard with baseline comparison."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.chunking import ChunkingService
from app.pipeline.feature_pipeline.cleaning import DocumentCleaningService
from app.pipeline.feature_pipeline.evaluation.stage_scorecard import StageScorecardService
from app.pipeline.feature_pipeline.parser import ParserRouter
from app.pipeline.feature_pipeline.schema_mapping import FinancialSchemaMappingService
from app.pipeline.feature_pipeline.segmentation import SemanticSegmentationService
from app.pipeline.feature_pipeline.structure_reconstruction import StructureReconstructionService
from app.pipeline.feature_pipeline.table_intelligence import TableIntelligenceService
from src.claude_copilot.schemas.document import DocumentMetadata

DEFAULT_PDF = Path(
    r"Z:/BaiduNetdiskDownload/阶段12：LLM大型复杂项目实战"
    r"/项目实战2：大模型金融对话交互系统/allpdf-part1"
    r"/2022-01-25__北京指南针科技发展股份有限公司__300803__指南针__2021年__年度报告.pdf"
)
EVAL_DIR = ROOT / "data" / "reports" / "eval"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage-wise document pipeline eval")
    parser.add_argument("--pdf-path", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=ROOT / "data" / "golden" / "znz_2021_stage_expectations.json",
    )
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--compare-baseline", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=EVAL_DIR / "latest_scorecard.json",
    )
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if not args.pdf_path.exists():
        raise FileNotFoundError(args.pdf_path)

    expectations = {}
    if args.expectations.exists():
        expectations = json.loads(args.expectations.read_text(encoding="utf-8"))

    content = args.pdf_path.read_bytes()
    metadata = DocumentMetadata(
        doc_type="annual_report",
        source="stage_eval",
        filename=args.pdf_path.name,
        extension=args.pdf_path.suffix.lower(),
        company="北京指南针科技发展股份有限公司",
        year=2021,
    )

    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    parsed = ParserRouter().parse(
        doc_id="stage-eval",
        filename=args.pdf_path.name,
        content=content,
        metadata=metadata,
    )
    timings["parse"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    cleaned = DocumentCleaningService().clean(parsed)
    timings["cleaning"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    segmented = SemanticSegmentationService().segment(cleaned)
    timings["segmentation"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    enhanced = TableIntelligenceService().enhance(segmented)
    enhanced = StructureReconstructionService().reconstruct(enhanced)
    schemed = FinancialSchemaMappingService().map(enhanced)
    timings["schema"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    segments = ChunkingService().chunk(schemed)
    timings["chunking"] = round(time.perf_counter() - t0, 3)

    scorecard = StageScorecardService().build(
        parsed=parsed,
        cleaned=cleaned,
        segmented=segmented,
        schemed=schemed,
        segments=segments,
        timings=timings,
        expectations=expectations,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(args.output), "summary_scores": scorecard["summary_scores"]}, ensure_ascii=False, indent=2))

    baseline_path = EVAL_DIR / "baseline_scorecard.json"
    if args.save_baseline:
        baseline_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"SAVED_BASELINE {baseline_path}")

    if args.compare_baseline:
        if not baseline_path.exists():
            print("NO_BASELINE: run with --save-baseline first")
            return 2
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        diff = StageScorecardService().compare(current=scorecard, baseline=baseline)
        diff_path = EVAL_DIR / "diff_vs_baseline.json"
        diff_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(diff, ensure_ascii=False, indent=2))
        print(f"WROTE {diff_path}")
        if diff["net_verdict"] == "negative":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluate manual external CER/TEDS golden against a parsed document artifact."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from lxml import html as lxml_html

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.feature_pipeline.evaluation.document_quality import (  # noqa: E402
    character_error_rate,
    table_teds,
)
from app.pipeline.feature_pipeline.parser.table_normalization import (  # noqa: E402
    normalize_currency_columns,
)

GOLDEN = ROOT / "data" / "golden" / "jpmc_2024_external_doc_quality.json"
OUT = ROOT / "data" / "reports" / "eval" / "jpmc_2024_external_doc_quality.json"


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    header = "".join(f"<th>{html.escape(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><tr>{header}</tr>{body}</table>"


def main() -> int:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    document = json.loads((ROOT / golden["parsed_document"]).read_text(encoding="utf-8"))
    table = next(
        item
        for item in document["tables"]
        if item.get("page") == golden["page"]
        and item.get("title") == golden["table_title"]
    )
    headers, rows = normalize_currency_columns(table["headers"], table["rows"])
    by_label = {row[0]: row for row in rows if row}
    selected_rows = [by_label[label] for label in golden["row_labels"]]
    prediction_html = _table_html(headers, selected_rows)
    reference_text = " ".join(lxml_html.fromstring(golden["reference_html"]).itertext())
    prediction_text = " ".join(lxml_html.fromstring(prediction_html).itertext())
    cer = character_error_rate(reference_text, prediction_text)
    teds = table_teds(golden["reference_html"], prediction_html)
    passed = cer <= golden["max_cer"] and teds >= golden["min_teds"]
    report = {
        "passed": passed,
        "source": golden["source"],
        "page": golden["page"],
        "cer": cer,
        "max_cer": golden["max_cer"],
        "teds": teds,
        "min_teds": golden["min_teds"],
        "predicted_columns": len(headers),
        "evaluated_rows": len(selected_rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

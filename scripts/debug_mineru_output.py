import argparse
import hashlib
import importlib
import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def import_mineru_module():
    for module_path in ("mineru.cli.common", "magic_pdf.cli.common"):
        try:
            return importlib.import_module(module_path)
        except Exception:
            continue
    raise RuntimeError("MinerU parse module is unavailable.")


def walk_json(value: Any, path: str = "$"):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{path}[{index}]")


def extract_text_like(item: dict[str, Any]) -> str:
    for key in ("text", "content", "md", "markdown", "html", "latex", "value", "caption"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    if isinstance(item.get("lines"), list):
        lines = [line.strip() for line in item["lines"] if isinstance(line, str) and line.strip()]
        if lines:
            return "\n".join(lines)

    return ""


def extract_page_number(item: dict[str, Any]) -> int | None:
    for key in ("page", "page_no", "page_num", "page_number", "page_idx"):
        value = item.get(key)
        if isinstance(value, int):
            return value + 1 if key == "page_idx" else value
        if isinstance(value, str) and value.isdigit():
            return int(value) + 1 if key == "page_idx" else int(value)
    return None


def raw_type_of(item: dict[str, Any]) -> str | None:
    raw_type = item.get("block_type") or item.get("type") or item.get("category_type") or item.get("label") or item.get("kind")
    return raw_type.strip() if isinstance(raw_type, str) and raw_type.strip() else None


def invoke_do_parse(*, pdf_path: Path, output_dir: Path, start_page_id: int, end_page_id: int | None) -> None:
    parse_module = import_mineru_module()
    do_parse = getattr(parse_module, "do_parse")
    params = inspect.signature(do_parse).parameters
    content = pdf_path.read_bytes()

    kwargs: dict[str, Any] = {}
    if "output_dir" in params:
        kwargs["output_dir"] = str(output_dir)
    if "pdf_file_names" in params:
        kwargs["pdf_file_names"] = [pdf_path.name]
    if "pdf_bytes_list" in params:
        kwargs["pdf_bytes_list"] = [content]
    if "pdf_bytes_md5_to_bytes" in params:
        content_md5 = hashlib.md5(content).hexdigest()  # noqa: S324
        kwargs["pdf_bytes_md5_to_bytes"] = {content_md5: content}
    if "p_lang_list" in params:
        kwargs["p_lang_list"] = ["ch"]
    if "parse_method" in params:
        kwargs["parse_method"] = "auto"
    if "formula_enable" in params:
        kwargs["formula_enable"] = True
    if "table_enable" in params:
        kwargs["table_enable"] = True
    if "start_page_id" in params:
        kwargs["start_page_id"] = start_page_id
    if "end_page_id" in params:
        kwargs["end_page_id"] = end_page_id

    output_dir.mkdir(parents=True, exist_ok=True)
    do_parse(**kwargs)


def analyze_json_files(output_dir: Path) -> None:
    json_files = sorted(output_dir.rglob("*.json"))
    print("json_files=", [str(path) for path in json_files])

    raw_type_counter: Counter[str] = Counter()
    table_like_by_path: Counter[str] = Counter()
    table_items: list[dict[str, Any]] = []

    for json_file in json_files:
        payload = json.loads(json_file.read_text(encoding="utf-8", errors="ignore"))
        for path, item in walk_json(payload):
            if not isinstance(item, dict):
                continue
            raw_type = raw_type_of(item)
            if raw_type:
                raw_type_counter[raw_type] += 1
            if raw_type and "table" in raw_type.lower():
                text = extract_text_like(item)
                table_like_by_path[path.split("[")[0]] += 1
                table_items.append(
                    {
                        "path": path,
                        "raw_type": raw_type,
                        "page": extract_page_number(item),
                        "text_len": len(text),
                        "text_preview": text[:120].replace("\n", " "),
                        "keys": sorted(item.keys()),
                    }
                )

    print("raw_type_top20=", raw_type_counter.most_common(20))
    print("table_like_by_path_top20=", table_like_by_path.most_common(20))

    grouped: defaultdict[tuple[int | None, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in table_items:
        grouped[(item["page"], item["raw_type"], item["text_preview"])].append(item)

    duplicates = [
        {"page": page, "raw_type": raw_type, "text_preview": preview, "count": len(items), "paths": [x["path"] for x in items[:8]]}
        for (page, raw_type, preview), items in grouped.items()
        if len(items) > 1
    ]
    duplicates.sort(key=lambda item: item["count"], reverse=True)

    print("duplicate_table_like_top20=", json.dumps(duplicates[:20], ensure_ascii=False, indent=2))
    print("sample_table_like_top20=", json.dumps(table_items[:20], ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-page-id", type=int, default=0)
    parser.add_argument("--end-page-id", type=int, default=4)
    parser.add_argument(
        "--pdf-path",
        type=Path,
        default=Path("data/fixtures/jpmc_audited_financial_statements_2024.pdf"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/debug/mineru_output"),
    )
    args = parser.parse_args()

    invoke_do_parse(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        start_page_id=args.start_page_id,
        end_page_id=args.end_page_id,
    )
    analyze_json_files(args.output_dir)


if __name__ == "__main__":
    main()

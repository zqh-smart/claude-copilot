"""Normalize parser table grids without changing financial semantics."""

from __future__ import annotations

import re

_CURRENCY_ONLY = re.compile(r"^[\s$€£¥￥]+$")


def normalize_currency_columns(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[str], list[list[str]]]:
    """Collapse an empty OCR currency column into its preceding period column."""
    width = len(headers)
    if width < 3:
        return headers, rows
    period_headers = [header for header in headers[1:] if header.strip()]
    has_empty_data_header = any(not header.strip() for header in headers[1:])
    if (
        has_empty_data_header
        and len(period_headers) >= 2
        and all(_looks_like_period(header) for header in period_headers)
    ):
        compacted_rows = []
        for row in rows:
            values = [cell.strip() for cell in row[1:] if _substantive(cell)]
            values = (values + [""] * len(period_headers))[: len(period_headers)]
            compacted_rows.append([row[0].strip() if row else "", *values])
        return [headers[0], *period_headers], compacted_rows
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    normalized_headers = list(headers)

    for index in range(width - 1, 0, -1):
        if normalized_headers[index].strip() or not normalized_headers[index - 1].strip():
            continue
        pairs = [(row[index - 1].strip(), row[index].strip()) for row in normalized_rows]
        if not any(_substantive(right) for _, right in pairs):
            continue
        if any(_substantive(left) and _substantive(right) for left, right in pairs):
            continue
        for row in normalized_rows:
            row[index - 1] = _merge_currency_cells(row[index - 1], row[index])
            del row[index]
        del normalized_headers[index]
        width -= 1

    return normalized_headers, normalized_rows


def _substantive(value: str) -> bool:
    return bool(value.strip()) and not bool(_CURRENCY_ONLY.fullmatch(value))


def _looks_like_period(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(
        re.fullmatch(r"(?:19|20)\d{2}", normalized)
        or normalized in {"current period", "prior period", "本期", "上期"}
    )


def _merge_currency_cells(left: str, right: str) -> str:
    left, right = left.strip(), right.strip()
    if _substantive(left):
        return left
    if _substantive(right):
        prefix = left if left and _CURRENCY_ONLY.fullmatch(left) else ""
        return " ".join(part for part in (prefix, right) if part)
    return left or right

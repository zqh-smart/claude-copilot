"""CER and TEDS metrics for manually annotated external document fixtures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apted import APTED, Config
from lxml import html


def character_error_rate(reference: str, prediction: str) -> float:
    reference = _normalize_text(reference)
    prediction = _normalize_text(prediction)
    return round(_levenshtein(reference, prediction) / max(len(reference), 1), 4)


def table_teds(reference_html: str, prediction_html: str) -> float:
    reference = _to_tree(reference_html)
    prediction = _to_tree(prediction_html)
    distance = APTED(reference, prediction, _TableConfig()).compute_edit_distance()
    return round(1.0 - distance / max(_tree_size(reference), _tree_size(prediction), 1), 4)


def _normalize_text(value: str) -> str:
    value = value.casefold().replace("−", "-").replace("–", "-")
    value = re.sub(r"[$€£¥￥,\s]", "", value)
    return value


def _levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


@dataclass
class _TableNode:
    tag: str
    content: str = ""
    colspan: str = "1"
    rowspan: str = "1"
    children: list["_TableNode"] = field(default_factory=list)


class _TableConfig(Config):
    def rename(self, node_a: _TableNode, node_b: _TableNode) -> float:
        if node_a.tag != node_b.tag:
            return 1.0
        if node_a.tag not in {"td", "th"}:
            return 0.0
        if (node_a.colspan, node_a.rowspan) != (node_b.colspan, node_b.rowspan):
            return 1.0
        left, right = _normalize_text(node_a.content), _normalize_text(node_b.content)
        return _levenshtein(left, right) / max(len(left), len(right), 1)


def _to_tree(table_html: str) -> _TableNode:
    root = html.fromstring(table_html)
    table = root if root.tag == "table" else root.find(".//table")
    if table is None:
        raise ValueError("TEDS input must contain a table")

    def convert(element) -> _TableNode:
        node = _TableNode(
            tag=element.tag,
            content=" ".join(element.itertext()) if element.tag in {"td", "th"} else "",
            colspan=element.attrib.get("colspan", "1"),
            rowspan=element.attrib.get("rowspan", "1"),
        )
        node.children = [
            convert(child)
            for child in element
            if child.tag in {"thead", "tbody", "tfoot", "tr", "td", "th"}
        ]
        return node

    return convert(table)


def _tree_size(node: _TableNode) -> int:
    return 1 + sum(_tree_size(child) for child in node.children)

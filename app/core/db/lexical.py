from __future__ import annotations

import re
from collections import Counter

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ALNUM_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English financial text for lexical retrieval."""
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    if not normalized:
        return []

    tokens: list[str] = []
    tokens.extend(_ALNUM_RE.findall(normalized))
    for run in _CJK_RE.findall(normalized):
        if len(run) <= 4:
            tokens.append(run)
        else:
            tokens.append(run)
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def bm25_lite_score(
    query_tokens: list[str],
    content: str,
    *,
    k1: float = 1.2,
    b: float = 0.75,
    avg_doc_len: float = 500.0,
) -> float:
    """BM25-style lexical score without corpus IDF (document-local TF + length norm)."""
    if not query_tokens:
        return 0.0

    content_tokens = tokenize(content)
    if not content_tokens:
        return 0.0

    term_freq = Counter(content_tokens)
    doc_len = len(content_tokens)
    query_terms = set(query_tokens)
    score = 0.0
    for term in query_terms:
        freq = term_freq.get(term, 0)
        if freq == 0:
            continue
        numerator = freq * (k1 + 1)
        denominator = freq + k1 * (1 - b + b * doc_len / max(avg_doc_len, 1.0))
        score += numerator / denominator

    return score / len(query_terms)

"""Browse Chat Memory L0/L1/L3 from MemoryCore local data dir (jsonl / persona).

Gateway ``/search/*`` is BM25-based and cannot list with ``query=*``.
Workbench layer browse therefore reads the same on-disk store the sidecar writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_NO_MATCH_PREFIXES = (
    "no matching conversation",
    "no matching memor",
    "no matching",
)


def is_empty_search_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lower = stripped.lower()
    return any(lower.startswith(prefix) for prefix in _NO_MATCH_PREFIXES)


def parse_gateway_search_results(raw: object, *, layer: str) -> list[dict[str, Any]]:
    """Normalize gateway ``results`` (often a formatted string) into item dicts."""
    if isinstance(raw, str):
        if is_empty_search_text(raw):
            return []
        return [{"content": raw, "layer": layer}]
    if isinstance(raw, list):
        items: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                if not is_empty_search_text(item):
                    items.append({"content": item, "layer": layer})
            elif isinstance(item, dict):
                items.append(item)
        return items
    if isinstance(raw, dict):
        return [raw]
    return []


def _session_matches(row: dict[str, Any], session_id: str | None) -> bool:
    if not session_id:
        return True
    sid = str(row.get("sessionId") or row.get("session_id") or "")
    skey = str(row.get("sessionKey") or row.get("session_key") or "")
    return session_id == sid or skey.endswith(f":{session_id}") or session_id in skey


def read_jsonl_layer(
    data_dir: Path,
    *,
    subdir: str,
    layer: str,
    session_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Read newest-first rows from ``data_dir/subdir/*.jsonl``."""
    root = data_dir / subdir
    if not root.is_dir():
        return []
    files = sorted(root.glob("*.jsonl"), reverse=True)
    matched: list[dict[str, Any]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if not _session_matches(row, session_id):
                continue
            item = dict(row)
            item.setdefault("layer", layer)
            matched.append(item)
            if len(matched) >= offset + limit:
                return matched[offset : offset + limit]
    return matched[offset : offset + limit]


def read_persona_items(data_dir: Path) -> list[dict[str, Any]]:
    """Collect persona.md files under ``profiles/`` for L3 browse."""
    profiles = data_dir / "profiles"
    if not profiles.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for persona in sorted(profiles.glob("**/persona.md")):
        try:
            content = persona.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        items.append(
            {
                "id": str(persona.relative_to(data_dir)),
                "content": content,
                "layer": "L3",
                "path": str(persona),
            }
        )
    return items


def list_scene_block_items(data_dir: Path, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """List L2 scene markdown files under profiles/scene_blocks and scene_blocks/."""
    roots: list[Path] = [data_dir / "scene_blocks"]
    profiles = data_dir / "profiles"
    if profiles.is_dir():
        roots.extend(sorted(profiles.glob("**/scene_blocks")))
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            items.append(
                {
                    "id": path.name,
                    "path": str(path.relative_to(data_dir)),
                    "content": content[:2000],
                    "layer": "L2",
                    "name": path.stem,
                }
            )
    return items[offset : offset + limit]

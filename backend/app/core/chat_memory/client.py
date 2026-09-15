"""HTTP client for MemoryCore Chat memory sidecar (recall / capture / health)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.chat_memory.formatter import empty_bundle, format_recall_context
from app.core.chat_memory.local_store import (
    list_scene_block_items,
    parse_gateway_search_results,
    read_jsonl_layer,
    read_persona_items,
)
from app.core.chat_memory.models import ChatMemoryBundle, RecalledMemory
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class HttpChatMemoryClient:
    """Talks to MemoryCore gateway ``POST /recall`` and ``POST /capture``.

    Failures never raise to the agent graph — they return empty bundles / no-op.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        timeout = max(0.5, self._settings.chat_memory_recall_timeout_ms / 1000.0)
        self._owns_client = client is None
        # trust_env=False: corporate HTTP_PROXY must not intercept loopback sidecar.
        self._client = client or httpx.Client(timeout=timeout, trust_env=False)
        self._base = self._settings.chat_memory_base_url.rstrip("/")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-tdai-service-id": self._settings.chat_memory_service_id,
            "x-tdai-team-id": self._settings.chat_memory_team_id,
            "x-tdai-agent-id": self._settings.chat_memory_agent_id,
            "x-tdai-user-id": self._settings.chat_memory_user_id,
        }
        if self._settings.chat_memory_api_key:
            headers["Authorization"] = f"Bearer {self._settings.chat_memory_api_key}"
        return headers

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get(f"{self._base}/health", headers=self._headers())
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return {"status": "up", **payload}
            return {"status": "up", "raw": payload}
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_memory health failed: %s", exc)
            return {"status": "down", "error": str(exc)}

    def recall(self, *, query: str, session_id: str | None) -> ChatMemoryBundle:
        from app.core.chat_memory.ids import session_key_for

        if not query.strip():
            return empty_bundle("empty_query")
        session_key = session_key_for(session_id or "default", settings=self._settings)
        timeout = max(0.5, self._settings.chat_memory_recall_timeout_ms / 1000.0)
        try:
            response = self._client.post(
                f"{self._base}/recall",
                headers=self._headers(),
                json={"query": query, "session_key": session_key},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_memory recall failed: %s", exc)
            return empty_bundle(f"recall_failed: {type(exc).__name__}")

        if not isinstance(data, dict):
            return empty_bundle("recall_invalid_payload")

        code = data.get("code", 0)
        warnings: list[str] = []
        if code not in (0, None, "0"):
            warnings.append(str(data.get("message") or f"recall_code={code}"))

        gateway_context = str(data.get("context") or "")
        raw_memories = data.get("memories") or data.get("results") or []
        memories: list[RecalledMemory] = []
        if isinstance(raw_memories, list):
            for item in raw_memories[: self._settings.chat_memory_recall_max_results]:
                if isinstance(item, str):
                    memories.append(RecalledMemory(content=item))
                    continue
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content") or item.get("text") or "").strip()
                if not content:
                    continue
                score = item.get("score")
                memories.append(
                    RecalledMemory(
                        content=content,
                        score=float(score) if isinstance(score, (int, float)) else None,
                        memory_type=str(item.get("type") or item.get("memory_type") or "")
                        or None,
                    )
                )

        prepend = format_recall_context(
            gateway_context=gateway_context,
            memories=memories,
            max_chars_per_memory=self._settings.chat_memory_max_chars_per_memory,
            max_total_chars=self._settings.chat_memory_max_total_recall_chars,
        )
        return ChatMemoryBundle(
            prepend=prepend,
            memories=memories,
            warnings=warnings,
            strategy=str(data.get("strategy") or "") or None,
            memory_count=int(data.get("memory_count") or len(memories) or 0),
        )

    def capture(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from app.core.chat_memory.ids import session_key_for

        if not self._settings.chat_memory_capture_enabled:
            return
        if not user_text.strip() or not assistant_text.strip():
            return
        session_key = session_key_for(session_id, settings=self._settings)
        body: dict[str, Any] = {
            "session_key": session_key,
            "session_id": session_id,
            "user_content": user_text,
            "assistant_content": assistant_text,
            "messages": [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ],
        }
        if metadata:
            body["metadata"] = metadata
        try:
            response = self._client.post(
                f"{self._base}/capture",
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_memory capture failed: %s", exc)

    def _isolation_fields(self) -> dict[str, str]:
        return {
            "team_id": self._settings.chat_memory_team_id,
            "agent_id": self._settings.chat_memory_agent_id,
            "user_id": self._settings.chat_memory_user_id,
        }

    def _post_dataplane(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST to MemoryCore; unwrap ``{code,data}`` envelopes when present."""
        response = self._client.post(
            f"{self._base}{path}",
            headers=self._headers(),
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return {"raw": payload}
        if "data" in payload and "code" in payload:
            code = payload.get("code")
            if code not in (0, None, "0"):
                raise RuntimeError(str(payload.get("message") or f"memory_code={code}"))
            data = payload.get("data")
            return data if isinstance(data, dict) else {"items": data}
        return payload

    def _data_dir(self) -> Path:
        return Path(self._settings.chat_memory_data_dir)

    def list_layer(
        self,
        *,
        layer: str,
        session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        layer_key = layer.upper()
        warnings: list[str] = []
        try:
            if layer_key == "L0":
                # Prefer on-disk jsonl (list); gateway search is BM25-only (no query=*).
                items = read_jsonl_layer(
                    self._data_dir(),
                    subdir="conversations",
                    layer="L0",
                    session_id=session_id,
                    limit=limit,
                    offset=offset,
                )
                if not items and session_id:
                    from app.core.chat_memory.ids import session_key_for

                    data = self._post_dataplane(
                        "/search/conversations",
                        {
                            "query": session_id,
                            "limit": limit,
                            "session_key": session_key_for(
                                session_id, settings=self._settings
                            ),
                        },
                    )
                    items = parse_gateway_search_results(
                        data.get("results") or data.get("items") or [],
                        layer="L0",
                    )
            elif layer_key == "L1":
                items = read_jsonl_layer(
                    self._data_dir(),
                    subdir="records",
                    layer="L1",
                    session_id=session_id,
                    limit=limit,
                    offset=offset,
                )
                if not items and session_id:
                    data = self._post_dataplane(
                        "/search/memories",
                        {"query": session_id, "limit": limit},
                    )
                    items = parse_gateway_search_results(
                        data.get("results") or data.get("items") or [],
                        layer="L1",
                    )
            elif layer_key == "L2":
                items = list_scene_block_items(
                    self._data_dir(), limit=limit, offset=offset
                )
                if not items:
                    try:
                        data = self._post_dataplane(
                            "/v2/scenario/ls",
                            {
                                **self._isolation_fields(),
                                "path_prefix": "",
                            },
                        )
                        items = data.get("entries") or data.get("items") or []
                        if offset or limit:
                            items = list(items)[offset : offset + limit]
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"v2_scenario_ls: {type(exc).__name__}")
                        items = []
            elif layer_key == "L3":
                items = read_persona_items(self._data_dir())
                if not items:
                    try:
                        data = self._post_dataplane(
                            "/v2/core/read",
                            {**self._isolation_fields()},
                        )
                        content = data.get("content") or data.get("text") or ""
                        items = (
                            [{"id": "core", "content": content, "layer": "L3"}]
                            if content
                            else []
                        )
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"v2_core_read: {type(exc).__name__}")
                        items = []
                if offset or (limit and len(items) > limit):
                    items = list(items)[offset : offset + limit]
            else:
                return {
                    "layer": layer_key,
                    "items": [],
                    "total": 0,
                    "status": "error",
                    "warnings": [f"unsupported_layer:{layer}"],
                }
            if not isinstance(items, list):
                items = [items]
            return {
                "layer": layer_key,
                "items": items,
                "total": len(items),
                "status": "ok",
                "warnings": warnings,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_memory list_layer(%s) failed: %s", layer_key, exc)
            return {
                "layer": layer_key,
                "items": [],
                "total": 0,
                "status": "down",
                "warnings": [f"list_layer_failed: {type(exc).__name__}"],
            }

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        del session_id  # gateway /search/memories is global to instance
        if not query.strip():
            return {"items": [], "total": 0, "status": "ok", "warnings": ["empty_query"]}
        try:
            # Prefer early gateway search (BM25/hybrid); fall back to v2 atomic search.
            try:
                data = self._post_dataplane(
                    "/search/memories",
                    {"query": query, "limit": limit},
                )
                items = parse_gateway_search_results(
                    data.get("results") or data.get("items") or [],
                    layer="L1",
                )
            except Exception:  # noqa: BLE001
                data = self._post_dataplane(
                    "/v2/atomic/search",
                    {
                        **self._isolation_fields(),
                        "query": query,
                        "limit": limit,
                    },
                )
                items = parse_gateway_search_results(
                    data.get("items") or data.get("results") or [],
                    layer="L1",
                )
            if not isinstance(items, list):
                items = [items]
            total = data.get("total")
            if not isinstance(total, int):
                total = len(items)
            return {
                "items": items,
                "total": total,
                "status": "ok",
                "strategy": data.get("strategy"),
                "warnings": [],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_memory search failed: %s", exc)
            return {
                "items": [],
                "total": 0,
                "status": "down",
                "warnings": [f"search_failed: {type(exc).__name__}"],
            }

"""Workbench proxy for MemoryCore Chat memory (not document KG)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_chat_memory_client
from app.core.chat_memory import ChatMemoryProtocol, NoopChatMemory
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/chat-memory", tags=["chat-memory"])

MemoryLayer = Literal["L0", "L1", "L2", "L3"]


class ChatMemoryCaptureRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_text: str = Field(min_length=1)
    assistant_text: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None


@router.get("/health")
def chat_memory_health(
    client: Annotated[ChatMemoryProtocol, Depends(get_chat_memory_client)],
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.chat_memory_enabled:
        return {
            "status": "disabled",
            "enabled": False,
            "base_url": settings.chat_memory_base_url,
            "reason": "CHAT_MEMORY_ENABLED=false",
        }
    payload = client.health()
    return {
        "enabled": True,
        "base_url": settings.chat_memory_base_url,
        **payload,
    }


@router.get("/layers/{layer}")
def list_chat_memory_layer(
    layer: MemoryLayer,
    client: Annotated[ChatMemoryProtocol, Depends(get_chat_memory_client)],
    session_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.chat_memory_enabled and isinstance(client, NoopChatMemory):
        return client.list_layer(
            layer=layer, session_id=session_id, limit=limit, offset=offset
        )
    return client.list_layer(
        layer=layer, session_id=session_id, limit=limit, offset=offset
    )


@router.get("/search")
def search_chat_memory(
    client: Annotated[ChatMemoryProtocol, Depends(get_chat_memory_client)],
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
    session_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return client.search(query=q, limit=limit, session_id=session_id)


@router.post("/capture")
def capture_chat_memory_turn(
    request: ChatMemoryCaptureRequest,
    client: Annotated[ChatMemoryProtocol, Depends(get_chat_memory_client)],
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.chat_memory_enabled:
        raise HTTPException(status_code=503, detail="chat memory disabled")
    if not settings.chat_memory_capture_enabled:
        raise HTTPException(status_code=503, detail="chat memory capture disabled")
    client.capture(
        session_id=request.session_id,
        user_text=request.user_text,
        assistant_text=request.assistant_text,
        metadata=request.metadata,
    )
    return {"status": "accepted", "session_id": request.session_id}

"""Chat conversation memory via MemoryCore sidecar (not document KG)."""

from app.core.chat_memory.client import HttpChatMemoryClient
from app.core.chat_memory.models import ChatMemoryBundle, RecalledMemory
from app.core.chat_memory.noop import NoopChatMemory
from app.core.chat_memory.protocol import ChatMemoryProtocol

__all__ = [
    "ChatMemoryBundle",
    "ChatMemoryProtocol",
    "HttpChatMemoryClient",
    "NoopChatMemory",
    "RecalledMemory",
]

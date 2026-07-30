from __future__ import annotations

import math
import re
import time
from hashlib import blake2b
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.errors import PersistenceBackendError


class EmbeddingServiceProtocol(Protocol):
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class HashEmbeddingService:
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_text(text)

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        features = self._extract_features(text)

        if not features:
            vector[0] = 1.0
            return vector

        for feature in features:
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.25 if feature.startswith("tok:") else 0.5
            vector[index] += sign * weight

        return self._normalize(vector)

    @staticmethod
    def _extract_features(text: str) -> list[str]:
        normalized = text.lower().strip()
        if not normalized:
            return []

        tokens = [token for token in re.split(r"\W+", normalized) if token]
        features = [f"tok:{token}" for token in tokens]

        compact = " ".join(tokens)
        if compact:
            features.extend(f"tri:{compact[i:i + 3]}" for i in range(max(0, len(compact) - 2)))
        return features

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


class SiliconEmbeddingService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        timeout: float = 60.0,
    ) -> None:
        self.dimensions = dimensions
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            trust_env=False,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = 32
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(self._embed_batch_with_retry(batch))
        self._validate_dimensions(vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def _embed_batch_with_retry(self, texts: list[str], *, attempts: int = 3) -> list[list[float]]:
        last_error: Exception | None = None
        payload = {
            "model": self._model,
            "input": [self._normalize_text(text) for text in texts],
        }
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.post("/embeddings", json=payload)
                response.raise_for_status()
                data = response.json().get("data", [])
                return [item["embedding"] for item in data]
            except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                time.sleep(1.5 * attempt)
        raise PersistenceBackendError(
            f"Silicon embedding request failed after {attempts} attempts: {last_error}"
        ) from last_error

    def _validate_dimensions(self, vectors: list[list[float]]) -> None:
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise PersistenceBackendError(
                    "Silicon embedding dimension mismatch: "
                    f"expected={self.dimensions}, actual={len(vector)}."
                )

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("\n", " ").strip()


def build_embedding_service(settings: Settings) -> EmbeddingServiceProtocol:
    backend = settings.embedding_backend

    if backend == "silicon":
        if not settings.silicon_key:
            raise PersistenceBackendError("EMBEDDING_BACKEND=silicon requires SILICON_KEY.")
        return SiliconEmbeddingService(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.embedding_model_id,
            dimensions=settings.embedding_dimensions,
        )

    if backend == "auto" and settings.silicon_key:
        return SiliconEmbeddingService(
            api_key=settings.silicon_key,
            base_url=settings.silicon_base_url,
            model=settings.embedding_model_id,
            dimensions=settings.embedding_dimensions,
        )

    return HashEmbeddingService(settings.embedding_dimensions)

"""Embedding client.

A small interface (`EmbeddingClient`) rather than calling a provider SDK
directly from the ingestion pipeline, so the pipeline doesn't know or care
which provider is configured — swapping providers later touches only this
file. This same interface will be reused unchanged by the retriever in
Phase 3 (queries are embedded the same way chunks are, by design — see
EDD §13 on preventing ingest/query skew).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from app.config.settings import settings
from app.data.models.chunk import EMBEDDING_DIMENSION


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text, same order."""


class OpenAIEmbeddingClient(EmbeddingClient):
    """Default real provider — text-embedding-3-small (1536 dimensions,
    matching the Chunk.embedding column's fixed width).
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        # Imported lazily so importing this module doesn't require the
        # openai package to be configured/importable unless this class is
        # actually instantiated (e.g. the "fake" provider path never
        # triggers this import).
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic, dependency-free embedding client.

    Not a mock — a real, if low-quality, embedding function: same text
    always produces the same vector, different text (almost always)
    produces a different one. Used by tests (no network/API key needed to
    prove the ingestion pipeline works end-to-end) and available for local
    development without an OpenAI key, so `docker compose up` stays fully
    functional with zero external dependencies (NFR1) even without real
    embeddings. Retrieval quality with this provider is not representative
    of the real one — it exists to prove the plumbing, not to be a
    genuine offline embedding model.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(EMBEDDING_DIMENSION)]


def get_embedding_client() -> EmbeddingClient:
    if settings.embedding_provider == "fake":
        return FakeEmbeddingClient()
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "COPILOT_OPENAI_API_KEY is required when COPILOT_EMBEDDING_PROVIDER=openai. "
                "Set COPILOT_EMBEDDING_PROVIDER=fake for local development or testing "
                "without a real API key."
            )
        return OpenAIEmbeddingClient(api_key=settings.openai_api_key)
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider!r}")

"""Embedding client.

A small interface (`EmbeddingClient`) rather than calling a provider SDK
directly from the ingestion pipeline, so the pipeline doesn't know or care
which provider is configured — swapping providers later touches only this
file. This same interface is reused unchanged by the retriever (queries
are embedded the same way chunks are, by design — see
PROJECT_HANDBOOK.md §2 on why mixing embedding sources for ingest vs.
query would degrade retrieval).

Every real provider must produce EMBEDDING_DIMENSION (1536)-length
vectors — Chunk.embedding is a fixed-width Postgres column, not something
a provider choice can silently resize. `GeminiEmbeddingClient` below
handles this by explicitly requesting 1536-dimension output (Gemini
supports this natively via Matryoshka Representation Learning — the model
is trained so a truncated prefix of its full embedding is still a valid,
useful embedding, not an arbitrary truncation) rather than accepting
whatever its default dimensionality happens to be.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from app.config.settings import settings
from app.data.models.chunk import EMBEDDING_DIMENSION


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text, same order."""


class OpenAIEmbeddingClient(EmbeddingClient):
    """text-embedding-3-small (1536 dimensions natively, matching the
    Chunk.embedding column's fixed width). Kept available per explicit
    decision even though `gemini` is the current real/demo embedding
    provider — not the default, but not removed either, since a real key
    may be added later. Preserved as a one-line config change
    (`COPILOT_EMBEDDING_PROVIDER=openai` + `COPILOT_OPENAI_API_KEY`) with
    zero code changes, exactly like every other provider here.
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


class GeminiEmbeddingClient(EmbeddingClient):
    """Default real/demo embedding provider. Uses Google's `google-genai`
    SDK, explicitly requesting `output_dimensionality=EMBEDDING_DIMENSION`
    (1536) so it slots into the existing `Chunk.embedding` column with no
    schema migration — confirmed this is a genuinely supported
    configuration (not a truncation hack) before choosing it: Gemini's
    embedding model is trained with Matryoshka Representation Learning
    specifically so shorter prefixes of the full embedding remain valid,
    high-quality embeddings on their own.

    One thing MRL truncation does NOT do automatically: preserve unit
    L2-norm. Google's own guidance is to re-normalize a truncated
    embedding before using it for cosine similarity — skipping this would
    silently degrade retrieval quality (a comparison that's supposed to
    be pure cosine similarity would be biased by inconsistent vector
    magnitudes). Done explicitly in `_normalize` below, not left to
    pgvector or the retriever to somehow compensate for.
    """

    _DEFAULT_MODEL = "gemini-embedding-001"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        # Imported lazily, same reasoning as OpenAIEmbeddingClient.
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model or self._DEFAULT_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        from google.genai import types

        response = self._client.models.embed_content(
            model=self._model,
            # The SDK's generated Union type for `contents` doesn't cleanly
            # accept `list[str]` under mypy's invariance rules, even though
            # a list of plain strings is the standard, documented call
            # shape — same category of SDK-typing friction already
            # documented for Anthropic's tool_choice overloads elsewhere in
            # this repo (see the removed AnthropicLLMClient's history in
            # PROJECT_PROGRESS.md).
            contents=texts,  # type: ignore[arg-type]
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini embed_content response contained no embeddings")
        return [self._normalize(e.values or []) for e in response.embeddings]

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        """L2-renormalizes a Matryoshka-truncated embedding back to unit
        norm — see class docstring for why this is required, not optional,
        after requesting a non-default output_dimensionality.
        """
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:
            return values
        return [v / norm for v in values]


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic, dependency-free embedding client.

    Not a mock — a real, if low-quality, embedding function: same text
    always produces the same vector, different text (almost always)
    produces a different one. Used by tests (no network/API key needed to
    prove the ingestion pipeline works end-to-end) and available for local
    development without a real provider key, so `docker compose up` stays
    fully functional with zero external dependencies (NFR1) even without
    real embeddings. Retrieval quality with this provider is not
    representative of the real one — it exists to prove the plumbing, not
    to be a genuine offline embedding model.
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
    if settings.embedding_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(
                "COPILOT_GEMINI_API_KEY is required when COPILOT_EMBEDDING_PROVIDER=gemini. "
                "Set COPILOT_EMBEDDING_PROVIDER=fake for local development or testing "
                "without a real API key."
            )
        return GeminiEmbeddingClient(api_key=settings.gemini_api_key)
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "COPILOT_OPENAI_API_KEY is required when COPILOT_EMBEDDING_PROVIDER=openai. "
                "Set COPILOT_EMBEDDING_PROVIDER=fake for local development or testing "
                "without a real API key."
            )
        return OpenAIEmbeddingClient(api_key=settings.openai_api_key)
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider!r}")

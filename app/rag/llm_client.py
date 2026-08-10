"""LLM client.

Mirrors app/rag/embedding_client.py's shape: a small interface
(`LLMClient`) rather than calling a provider SDK directly from the
orchestrator, so the orchestrator doesn't know or care which provider is
configured. The real provider is Claude via Anthropic's Messages API (EDD
§15); a "fake" provider (same precedent as FakeEmbeddingClient) exists
for tests and for standalone/no-API-key local runs.

Citation strategy: rather than having the model answer in free text and
then trying to reverse-engineer which chunks it drew from, the model is
forced (tool_choice) to call a single tool whose schema requires it to
name the chunk_ids it's citing and self-rate its confidence that the
answer is fully supported by them. This is more reliable than post-hoc
text matching — there's no risk of matching a citation to the wrong chunk
because of similar wording — at the cost of depending on the provider's
tool-use support. See app/rag/citation_extractor.py for how a
model-reported chunk_id that doesn't correspond to a retrieved chunk (a
hallucinated citation) is handled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config.settings import settings

_ANSWER_TOOL_NAME = "provide_answer"

_ANSWER_TOOL = {
    "name": _ANSWER_TOOL_NAME,
    "description": (
        "Provide a grounded answer to the maintenance question using only the "
        "supplied context chunks, along with the chunk_ids actually relied on "
        "and a self-rated confidence."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer, written for a maintenance technician. If the "
                "context doesn't support an answer, say so plainly instead of guessing.",
            },
            "cited_chunk_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "chunk_id values (from the supplied context) that directly "
                "support the answer. Empty if the context doesn't support an answer.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Self-rated confidence (0-1) that the answer is fully and "
                "correctly supported by the cited chunks.",
            },
        },
        "required": ["answer", "cited_chunk_ids", "confidence"],
    },
}


@dataclass(frozen=True)
class LLMAnswer:
    answer_text: str
    cited_chunk_ids: list[str]
    self_rated_confidence: float


class LLMClient(ABC):
    @abstractmethod
    def generate_answer(
        self, system_prompt: str, user_prompt: str, chunk_ids: list[str]
    ) -> LLMAnswer:
        """Returns a structured, self-cited answer for one question.

        `chunk_ids` is the full list of retrieved candidate ids (the same
        ones already embedded as `[chunk_id: ...]` markers inside
        `user_prompt` by app/rag/prompt_builder.py). A real provider is
        expected to read ids back out of the prompt content itself, per
        the citation contract in the tool schema above; the parameter
        exists so a deterministic test client doesn't need to
        reverse-engineer ids out of prompt text to return something
        realistic.
        """


class AnthropicLLMClient(LLMClient):
    """Default real provider — Claude via the Messages API (EDD §15)."""

    def __init__(self, api_key: str, model: str) -> None:
        # Imported lazily, same reasoning as OpenAIEmbeddingClient: importing
        # this module shouldn't require the anthropic package to be
        # configured unless this class is actually instantiated.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def generate_answer(
        self, system_prompt: str, user_prompt: str, chunk_ids: list[str]
    ) -> LLMAnswer:
        # The SDK's overloaded `.create` wants its own TypedDicts (ToolParam,
        # ToolChoiceToolParam) for `tools`/`tool_choice`; a plain dict
        # literal matches their shape exactly at runtime but mypy can't
        # verify that through the overload set — ignored below.
        response = self._client.messages.create(  # type: ignore[call-overload]
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[_ANSWER_TOOL],
            tool_choice={"type": "tool", "name": _ANSWER_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == _ANSWER_TOOL_NAME:
                payload = block.input
                return LLMAnswer(
                    answer_text=str(payload["answer"]),
                    cited_chunk_ids=[str(c) for c in payload.get("cited_chunk_ids", [])],
                    self_rated_confidence=float(payload["confidence"]),
                )
        # Forced tool_choice makes this unreachable in practice; guarded
        # explicitly rather than letting a KeyError surface from below.
        raise RuntimeError("Anthropic response did not include the expected tool_use block")


class FakeLLMClient(LLMClient):
    """Deterministic, dependency-free LLM client.

    Same role as FakeEmbeddingClient: not a mock, a real (if trivial)
    implementation that proves the orchestrator's plumbing — prompt in,
    structured answer out — without a network call or API key. It cites
    every chunk_id it was given and returns a fixed confidence, which is
    enough for tests to exercise citation extraction and confidence
    scoring meaningfully. Answer quality/relevance with this provider is
    not representative of the real one — see EmbeddingClient's docstring
    for the same caveat applied to embeddings.
    """

    _FIXED_CONFIDENCE = 0.8

    def generate_answer(
        self, system_prompt: str, user_prompt: str, chunk_ids: list[str]
    ) -> LLMAnswer:
        answer_text = (
            "This is a deterministic fake answer generated without a real LLM call, "
            f"grounded in {len(chunk_ids)} retrieved chunk(s)."
        )
        return LLMAnswer(
            answer_text=answer_text,
            cited_chunk_ids=list(chunk_ids),
            self_rated_confidence=self._FIXED_CONFIDENCE,
        )


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "COPILOT_ANTHROPIC_API_KEY is required when COPILOT_LLM_PROVIDER=anthropic. "
                "Set COPILOT_LLM_PROVIDER=fake for local development or testing without a "
                "real API key."
            )
        return AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.llm_model)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")

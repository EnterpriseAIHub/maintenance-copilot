"""LLM client.

Mirrors app/rag/embedding_client.py's shape: a small interface
(`LLMClient`) rather than calling a provider SDK directly from the
orchestrator, so the orchestrator doesn't know or care which provider is
configured. Supported providers: `fake` (tests/no-key local runs),
`groq` (default real/demo provider), `gemini`, and `openai` (kept
available for future use — see each client's own docstring for why it
exists even though it isn't the demo default).

Anthropic support has been removed entirely (previously the only real
provider, Phases 3-6) per a later provider-strategy decision — see
PROJECT_PROGRESS.md's "Provider migration" section for the full record
of what changed and why. There is no Anthropic code, setting, dependency,
or env var left anywhere in this repo.

Citation strategy (unchanged by this migration): rather than having the
model answer in free text and then trying to reverse-engineer which
chunks it drew from, the model is forced (tool/function-choice) to call a
single tool whose schema requires it to name the chunk_ids it's citing
and self-rate its confidence that the answer is fully supported by them.
Every real provider below implements this same forced-call contract
through whatever mechanism that provider's API uses for it — the
orchestrator and everything above this module is completely unaware of
the difference. See app/rag/citation_extractor.py for how a
model-reported chunk_id that doesn't correspond to a retrieved chunk (a
hallucinated citation) is handled.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.config.settings import settings

_ANSWER_TOOL_NAME = "provide_answer"

_ANSWER_TOOL_DESCRIPTION = (
    "Provide a grounded answer to the maintenance question using only the "
    "supplied context chunks, along with the chunk_ids actually relied on "
    "and a self-rated confidence."
)

# The JSON Schema for the forced tool/function call, shared verbatim
# across every real provider below — each provider's SDK wants this
# wrapped slightly differently (Anthropic wanted `input_schema`;
# OpenAI-compatible SDKs and Gemini both want `parameters`), but the
# schema body itself is identical everywhere, so it's defined once here
# rather than duplicated per provider.
_ANSWER_TOOL_PARAMETERS: dict[str, Any] = {
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


def _parse_tool_arguments(payload: dict[str, Any]) -> LLMAnswer:
    """Shared response parsing for every real provider — each one hands
    this module a plain dict of the tool/function call's arguments
    (already provider-specific-parsed by the caller), and this is the one
    place that turns that dict into an LLMAnswer, so the
    answer/cited_chunk_ids/confidence field names only need to be typed
    once.
    """
    return LLMAnswer(
        answer_text=str(payload["answer"]),
        cited_chunk_ids=[str(c) for c in payload.get("cited_chunk_ids", [])],
        self_rated_confidence=float(payload["confidence"]),
    )


class _OpenAICompatibleLLMClient(LLMClient):
    """Shared implementation for any provider whose chat-completions API
    is wire-compatible with OpenAI's (tools/tool_choice shape identical)
    — currently `OpenAILLMClient` and `GroqLLMClient`. Only client
    construction (which SDK class, which api_key) and the default model
    differ between them; the actual request/response handling is
    identical, so it lives here once rather than being duplicated.
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def generate_answer(
        self, system_prompt: str, user_prompt: str, chunk_ids: list[str]
    ) -> LLMAnswer:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": _ANSWER_TOOL_NAME,
                        "description": _ANSWER_TOOL_DESCRIPTION,
                        "parameters": _ANSWER_TOOL_PARAMETERS,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": _ANSWER_TOOL_NAME}},
        )
        message = response.choices[0].message
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == _ANSWER_TOOL_NAME:
                    return _parse_tool_arguments(json.loads(tool_call.function.arguments))
        # Forced tool_choice makes this unreachable in practice; guarded
        # explicitly rather than letting an IndexError/KeyError surface.
        raise RuntimeError(
            f"{type(self._client).__module__} response did not include the expected tool call"
        )


class OpenAILLMClient(_OpenAICompatibleLLMClient):
    """Kept available per explicit decision, even though `groq` is the
    current real/demo provider — not the default, but not removed either.
    Preserved so it's a one-line config change (`COPILOT_LLM_PROVIDER=openai`
    + `COPILOT_OPENAI_API_KEY`) to switch to it later, with zero code
    changes, exactly like every other provider here. This is a distinct
    concern from `OpenAIEmbeddingClient` in embedding_client.py — that one
    handles embeddings, this one handles chat/generation; they share the
    `openai` SDK and `COPILOT_OPENAI_API_KEY`, nothing else.
    """

    _DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str, model: str | None) -> None:
        # Imported lazily, same reasoning as OpenAIEmbeddingClient: importing
        # this module shouldn't require the openai package to be
        # configured unless this class is actually instantiated.
        from openai import OpenAI

        super().__init__(OpenAI(api_key=api_key), model or self._DEFAULT_MODEL)


class GroqLLMClient(_OpenAICompatibleLLMClient):
    """Default real/demo provider. Groq's chat completions API is
    wire-compatible with OpenAI's (same tools/tool_choice shape,
    confirmed directly against the installed `groq` SDK's type signatures
    before writing this), so this is a thin subclass of
    _OpenAICompatibleLLMClient rather than a separate implementation.
    """

    _DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str, model: str | None) -> None:
        from groq import Groq

        super().__init__(Groq(api_key=api_key), model or self._DEFAULT_MODEL)


class GeminiLLMClient(LLMClient):
    """Uses Google's `google-genai` SDK. Forced tool calling here works
    differently from the OpenAI-compatible shape above — Gemini expects a
    `ToolConfig` with `function_calling_config.mode=ANY` plus
    `allowed_function_names`, not a `tool_choice` field on the request
    itself. Confirmed directly against the installed SDK's actual type
    signatures (`FunctionCallingConfigMode.ANY`, `FunctionDeclaration`,
    `EmbedContentConfig`, etc.) before writing this, not assumed from
    memory — API shapes like this are exactly the kind of detail worth
    getting wrong silently, so this wasn't guessed.
    """

    _DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str | None) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model or self._DEFAULT_MODEL

    def generate_answer(
        self, system_prompt: str, user_prompt: str, chunk_ids: list[str]
    ) -> LLMAnswer:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[
                    types.Tool(
                        function_declarations=[
                            types.FunctionDeclaration(
                                name=_ANSWER_TOOL_NAME,
                                description=_ANSWER_TOOL_DESCRIPTION,
                                parameters_json_schema=_ANSWER_TOOL_PARAMETERS,
                            )
                        ]
                    )
                ],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY,
                        allowed_function_names=[_ANSWER_TOOL_NAME],
                    )
                ),
            ),
        )
        for call in response.function_calls or []:
            if call.name == _ANSWER_TOOL_NAME:
                return _parse_tool_arguments(dict(call.args or {}))
        # Forced mode=ANY + allowed_function_names makes this unreachable
        # in practice; guarded explicitly rather than letting this raise
        # an opaque IndexError/AttributeError from below.
        raise RuntimeError("Gemini response did not include the expected function call")


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
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError(
                "COPILOT_GROQ_API_KEY is required when COPILOT_LLM_PROVIDER=groq. "
                "Set COPILOT_LLM_PROVIDER=fake for local development or testing without a "
                "real API key."
            )
        return GroqLLMClient(api_key=settings.groq_api_key, model=settings.llm_model)
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(
                "COPILOT_GEMINI_API_KEY is required when COPILOT_LLM_PROVIDER=gemini. "
                "Set COPILOT_LLM_PROVIDER=fake for local development or testing without a "
                "real API key."
            )
        return GeminiLLMClient(api_key=settings.gemini_api_key, model=settings.llm_model)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "COPILOT_OPENAI_API_KEY is required when COPILOT_LLM_PROVIDER=openai. "
                "Set COPILOT_LLM_PROVIDER=fake for local development or testing without a "
                "real API key."
            )
        return OpenAILLMClient(api_key=settings.openai_api_key, model=settings.llm_model)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")

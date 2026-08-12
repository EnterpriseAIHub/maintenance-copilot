"""Request/response *shape* verification for the real LLM providers,
without any real network call.

These tests exist because getting an SDK's request/response shape wrong
is a real, silent-failure-prone risk with multi-provider abstractions —
the code can look reasonable and still be wrong about exactly which
nested field a tool call's arguments live in. Each test here either (a)
constructs the real SDK request object the client sends, proving the
SDK's own validation accepts the shape (catches schema mistakes without
a network call), or (b) feeds a manually-constructed but realistically-
shaped response object through the client's own parsing logic (catches
response-parsing mistakes the same way). No API key, no network access,
no real provider call — these run in the normal fake-only test suite.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.rag.llm_client import (
    _ANSWER_TOOL_DESCRIPTION,
    _ANSWER_TOOL_NAME,
    _ANSWER_TOOL_PARAMETERS,
    GeminiLLMClient,
    GroqLLMClient,
    LLMAnswer,
    OpenAILLMClient,
    _parse_tool_arguments,
)


def _make_openai_compatible_tool_call_response(arguments: dict) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.name = _ANSWER_TOOL_NAME
    tool_call.function.arguments = json.dumps(arguments)
    message = MagicMock()
    message.tool_calls = [tool_call]
    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    return response


class TestOpenAICompatibleShape:
    """Covers both GroqLLMClient and OpenAILLMClient — they share the
    exact same request/response handling (_OpenAICompatibleLLMClient),
    so one test class parametrized over both proves both at once rather
    than duplicating each case.
    """

    def _clients(self) -> list:
        return [
            GroqLLMClient(api_key="dummy", model=None),
            OpenAILLMClient(api_key="dummy", model=None),
        ]

    def test_request_uses_forced_tool_choice_with_correct_shape(self) -> None:
        for client in self._clients():
            client._client.chat.completions.create = MagicMock(
                return_value=_make_openai_compatible_tool_call_response(
                    {"answer": "a", "cited_chunk_ids": [], "confidence": 0.5}
                )
            )

            client.generate_answer("system prompt", "user prompt", [])

            call_kwargs = client._client.chat.completions.create.call_args.kwargs
            assert call_kwargs["tool_choice"] == {
                "type": "function",
                "function": {"name": _ANSWER_TOOL_NAME},
            }
            [tool] = call_kwargs["tools"]
            assert tool["type"] == "function"
            assert tool["function"]["name"] == _ANSWER_TOOL_NAME
            assert tool["function"]["description"] == _ANSWER_TOOL_DESCRIPTION
            assert tool["function"]["parameters"] == _ANSWER_TOOL_PARAMETERS

    def test_request_sends_system_and_user_messages(self) -> None:
        client = GroqLLMClient(api_key="dummy", model=None)
        client._client.chat.completions.create = MagicMock(
            return_value=_make_openai_compatible_tool_call_response(
                {"answer": "a", "cited_chunk_ids": [], "confidence": 0.5}
            )
        )

        client.generate_answer("system prompt", "user prompt", [])

        messages = client._client.chat.completions.create.call_args.kwargs["messages"]
        assert messages == [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ]

    def test_parses_tool_call_arguments_into_llm_answer(self) -> None:
        for client in self._clients():
            client._client.chat.completions.create = MagicMock(
                return_value=_make_openai_compatible_tool_call_response(
                    {
                        "answer": "Lubricate every 2000 hours.",
                        "cited_chunk_ids": ["chunk-1", "chunk-2"],
                        "confidence": 0.87,
                    }
                )
            )

            result = client.generate_answer("system", "user", ["chunk-1", "chunk-2"])

            assert result == LLMAnswer(
                answer_text="Lubricate every 2000 hours.",
                cited_chunk_ids=["chunk-1", "chunk-2"],
                self_rated_confidence=0.87,
            )

    def test_raises_if_no_matching_tool_call_present(self) -> None:
        client = GroqLLMClient(api_key="dummy", model=None)
        message = MagicMock()
        message.tool_calls = []
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        client._client.chat.completions.create = MagicMock(return_value=response)

        try:
            client.generate_answer("system", "user", [])
            raised = False
        except RuntimeError:
            raised = True
        assert raised


class TestGeminiShape:
    def test_generate_content_config_is_accepted_by_the_real_sdk_types(self) -> None:
        # Builds the exact config object GeminiLLMClient.generate_answer
        # constructs — the google-genai SDK's pydantic models raise
        # immediately on construction if the shape is wrong, so this
        # catches a schema mistake without any network call.
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction="system prompt",
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
        )

        assert config.tool_config.function_calling_config.mode == (
            types.FunctionCallingConfigMode.ANY
        )
        assert config.tool_config.function_calling_config.allowed_function_names == [
            _ANSWER_TOOL_NAME
        ]

    def test_embed_content_config_accepts_the_fixed_dimension(self) -> None:
        from google.genai import types

        from app.data.models.chunk import EMBEDDING_DIMENSION

        config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)

        assert config.output_dimensionality == EMBEDDING_DIMENSION

    def test_parses_function_call_args_into_llm_answer(self) -> None:
        from google.genai import types

        call = types.FunctionCall(
            name=_ANSWER_TOOL_NAME,
            args={
                "answer": "Every 2000 hours.",
                "cited_chunk_ids": ["chunk-1"],
                "confidence": 0.9,
            },
        )

        result = _parse_tool_arguments(dict(call.args or {}))

        assert result == LLMAnswer(
            answer_text="Every 2000 hours.",
            cited_chunk_ids=["chunk-1"],
            self_rated_confidence=0.9,
        )

    def test_raises_if_no_matching_function_call_present(self) -> None:
        client = GeminiLLMClient(api_key="dummy", model=None)
        client._client.models.generate_content = MagicMock(
            return_value=MagicMock(function_calls=[])
        )

        try:
            client.generate_answer("system", "user", [])
            raised = False
        except RuntimeError:
            raised = True
        assert raised

"""Unit tests for the LLM client interface, factory, and provider
construction. No real API calls anywhere in this file — real-provider
tests only check factory selection, missing-key errors, and client
construction (which SDK client classes accept credentials without
making a network call), never an actual generate_answer() against a
live API. See tests/unit/test_provider_request_shapes.py for
request/response *shape* verification (also without real network calls,
via mocked/simulated SDK objects).
"""

from __future__ import annotations

import pytest

from app.rag.llm_client import (
    FakeLLMClient,
    GeminiLLMClient,
    GroqLLMClient,
    LLMAnswer,
    OpenAILLMClient,
    get_llm_client,
)


def test_fake_client_cites_every_provided_chunk_id() -> None:
    client = FakeLLMClient()
    chunk_ids = ["chunk-a", "chunk-b"]

    result = client.generate_answer("system", "user", chunk_ids)

    assert isinstance(result, LLMAnswer)
    assert result.cited_chunk_ids == chunk_ids


def test_fake_client_returns_fixed_confidence() -> None:
    client = FakeLLMClient()

    result = client.generate_answer("system", "user", [])

    assert result.self_rated_confidence == pytest.approx(0.8)


def test_fake_client_answer_mentions_chunk_count() -> None:
    client = FakeLLMClient()

    result = client.generate_answer("system", "user", ["a", "b", "c"])

    assert "3" in result.answer_text


def test_factory_returns_fake_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "fake")

    client = get_llm_client()

    assert isinstance(client, FakeLLMClient)


def test_factory_returns_groq_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "groq")
    monkeypatch.setattr("app.rag.llm_client.settings.groq_api_key", "dummy-key")

    client = get_llm_client()

    assert isinstance(client, GroqLLMClient)


def test_factory_raises_without_api_key_for_groq_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "groq")
    monkeypatch.setattr("app.rag.llm_client.settings.groq_api_key", None)

    with pytest.raises(RuntimeError, match="COPILOT_GROQ_API_KEY"):
        get_llm_client()


def test_factory_returns_gemini_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "gemini")
    monkeypatch.setattr("app.rag.llm_client.settings.gemini_api_key", "dummy-key")

    client = get_llm_client()

    assert isinstance(client, GeminiLLMClient)


def test_factory_raises_without_api_key_for_gemini_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "gemini")
    monkeypatch.setattr("app.rag.llm_client.settings.gemini_api_key", None)

    with pytest.raises(RuntimeError, match="COPILOT_GEMINI_API_KEY"):
        get_llm_client()


def test_factory_returns_openai_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "openai")
    monkeypatch.setattr("app.rag.llm_client.settings.openai_api_key", "dummy-key")

    client = get_llm_client()

    assert isinstance(client, OpenAILLMClient)


def test_factory_raises_without_api_key_for_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "openai")
    monkeypatch.setattr("app.rag.llm_client.settings.openai_api_key", None)

    with pytest.raises(RuntimeError, match="COPILOT_OPENAI_API_KEY"):
        get_llm_client()


def test_factory_raises_for_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "not-a-real-provider")

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_client()


def test_factory_raises_for_anthropic_as_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic support has been removed entirely (see
    PROJECT_PROGRESS.md's "Provider migration" section) — "anthropic" is
    no longer a recognized provider value at all, not even one that
    raises a provider-specific "missing key" error. This is the
    regression test for that removal actually being complete.
    """
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "anthropic")

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_client()


def test_groq_client_defaults_to_llama_model_when_not_overridden() -> None:
    client = GroqLLMClient(api_key="dummy", model=None)

    assert client._model == "llama-3.3-70b-versatile"


def test_groq_client_uses_explicit_model_override_when_given() -> None:
    client = GroqLLMClient(api_key="dummy", model="some-other-groq-model")

    assert client._model == "some-other-groq-model"


def test_gemini_client_defaults_to_flash_model_when_not_overridden() -> None:
    client = GeminiLLMClient(api_key="dummy", model=None)

    assert client._model == "gemini-2.5-flash"


def test_openai_client_defaults_to_gpt4o_mini_when_not_overridden() -> None:
    client = OpenAILLMClient(api_key="dummy", model=None)

    assert client._model == "gpt-4o-mini"

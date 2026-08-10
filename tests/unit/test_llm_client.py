from __future__ import annotations

import pytest

from app.rag.llm_client import FakeLLMClient, LLMAnswer, get_llm_client


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


def test_factory_raises_without_api_key_for_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "anthropic")
    monkeypatch.setattr("app.rag.llm_client.settings.anthropic_api_key", None)

    with pytest.raises(RuntimeError, match="COPILOT_ANTHROPIC_API_KEY"):
        get_llm_client()


def test_factory_raises_for_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.llm_client.settings.llm_provider", "not-a-real-provider")

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_client()

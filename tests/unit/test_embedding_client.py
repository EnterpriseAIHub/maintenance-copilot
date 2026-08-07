from __future__ import annotations

import pytest

from app.data.models.chunk import EMBEDDING_DIMENSION
from app.rag.embedding_client import FakeEmbeddingClient, get_embedding_client


def test_fake_client_returns_correct_dimension() -> None:
    client = FakeEmbeddingClient()

    [embedding] = client.embed(["a pump manual excerpt"])

    assert len(embedding) == EMBEDDING_DIMENSION


def test_fake_client_is_deterministic() -> None:
    client = FakeEmbeddingClient()

    first = client.embed(["the same text"])
    second = client.embed(["the same text"])

    assert first == second


def test_fake_client_differs_for_different_text() -> None:
    client = FakeEmbeddingClient()

    [a] = client.embed(["vibration troubleshooting"])
    [b] = client.embed(["hydraulic pressure loss"])

    assert a != b


def test_fake_client_preserves_input_order() -> None:
    client = FakeEmbeddingClient()

    embeddings = client.embed(["first", "second", "third"])

    assert embeddings[0] == client.embed(["first"])[0]
    assert embeddings[2] == client.embed(["third"])[0]


def test_factory_returns_fake_client_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.embedding_client.settings.embedding_provider", "fake")

    client = get_embedding_client()

    assert isinstance(client, FakeEmbeddingClient)


def test_factory_raises_without_api_key_for_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.embedding_client.settings.embedding_provider", "openai")
    monkeypatch.setattr("app.rag.embedding_client.settings.openai_api_key", None)

    with pytest.raises(RuntimeError, match="COPILOT_OPENAI_API_KEY"):
        get_embedding_client()


def test_factory_raises_for_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rag.embedding_client.settings.embedding_provider", "not-a-real-provider"
    )

    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedding_client()

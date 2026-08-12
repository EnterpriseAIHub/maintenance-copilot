"""Application configuration.

All runtime config comes from environment variables (or a local .env file),
never from hardcoded values, per the EDD's development standards. Every
variable is prefixed COPILOT_ so this repo can be composed alongside other
Enterprise AI Platform repos (e.g. predictive-maintenance) without
environment-variable collisions.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    environment: str = "local"
    log_level: str = "INFO"

    # --- Database (Postgres + pgvector, one store for relational data and
    # vectors — see EDD §11, §15) ---
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"

    # --- RAG providers ---
    # llm_provider: "groq" (default real/demo provider), "gemini",
    # "openai" (kept available for future use, not the demo default), or
    # "fake" (deterministic, no network/API key required — used by tests
    # and available for local development without any real provider key).
    # Anthropic support has been removed entirely — see
    # PROJECT_PROGRESS.md's "Provider migration" section for the record
    # of that decision. `llm_model` is a single override shared across
    # whichever provider is active; each real client has its own sensible
    # hardcoded default model, so switching COPILOT_LLM_PROVIDER alone
    # (without also having to remember to change the model string) just
    # works.
    llm_provider: str = "groq"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    llm_model: str | None = None
    # embedding_provider: "gemini" (default real/demo provider), "openai"
    # (kept available for future use, not the demo default — preserves
    # the original real embedding provider from earlier phases), or
    # "fake" (deterministic, no network/API key required — used by tests,
    # and available for local development without a real provider key so
    # this repo stays runnable standalone per NFR1).
    embedding_provider: str = "gemini"
    openai_api_key: str | None = None
    confidence_threshold: float = 0.55
    # Number of chunks the retriever returns per query (Phase 3). Added
    # now, alongside the retriever that's the first thing to read it — not
    # added speculatively ahead of need.
    retrieval_top_k: int = 5
    # Number of most-recent message pairs (Phase 4) loaded from a
    # conversation's history and passed to the LLM as prompt context for
    # follow-up questions — see app/services/conversation_service.py.
    # Bounded rather than unbounded so prompt size/cost don't grow
    # unboundedly as a conversation gets long.
    conversation_history_limit: int = 6

    # --- Document ingestion (Phase 2) ---
    # Where uploaded source files are stored on disk. Relative to the
    # container/process working directory. See docker-compose.yml for the
    # volume mount that persists this across container restarts.
    document_storage_path: str = "data/raw/documents"

    # --- Cross-repo integration (Phase 6). Optional and unset by default:
    # this repo must run standalone with zero other repos present (NFR1).
    # When set, it points at a running predictive-maintenance instance for
    # the optional GET /equipment/{id}/risk enrichment call. ---
    predictive_maintenance_base_url: str | None = None
    # Bounds the worst-case latency this one optional call can add to a
    # request. This call happens synchronously within the same
    # request/response cycle as the rest of the answer (see
    # app/services/conversation_service.py) — its latency is a direct,
    # real contributor to this repo's own response-time P95, not a
    # fire-and-forget background call. An unbounded or slow
    # predictive-maintenance instance must not itself be able to push
    # this repo's P95 past NFR2's target ("full grounded answer targets
    # P95 under ~5s" — confirmed against the actual EDD, not guessed:
    # see PROJECT_PROGRESS.md's architectural review notes). 1.0s was
    # chosen — tightened down from an initial 1.5s guess made before the
    # EDD was available — to keep this one optional call from consuming
    # too large a share of that 5s budget: enough time for a real
    # round-trip to a healthy service, without eating into the headroom
    # the actual RAG pipeline (retrieval + LLM generation) needs to stay
    # under NFR2 on its own.
    predictive_maintenance_timeout_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Using a function (rather than a module-level singleton constructed at
    import time) makes it straightforward to override settings in tests via
    dependency overrides or by clearing the cache, without needing to
    monkeypatch a module attribute.
    """
    return Settings()


settings = get_settings()

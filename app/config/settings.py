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
    # llm_provider is unused until Phase 3; kept here so the config shape is
    # stable across phases.
    llm_provider: str = "anthropic"
    # embedding_provider: "openai" (default, real embeddings) or "fake"
    # (deterministic, no network/API key required — used by tests, and
    # available for local development without an OpenAI key so this repo
    # stays runnable standalone per NFR1 even without a real provider key).
    embedding_provider: str = "openai"
    openai_api_key: str | None = None
    confidence_threshold: float = 0.55

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

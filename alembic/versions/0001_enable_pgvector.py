"""enable pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-08-02

Baseline migration for Phase 1. Enables the pgvector extension so that the
`chunk` table added in Phase 2 can use a native VECTOR column — one store
for both relational data and embeddings, per EDD §11/§15 (no separate
vector database service).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")

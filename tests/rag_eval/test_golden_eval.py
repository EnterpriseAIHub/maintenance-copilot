"""Golden-dataset RAG evaluation harness (Phase 3 exit criterion).

Ingests the two synthetic seed documents in data/seed/ using the REAL
embedding and LLM providers (not the fake ones — see the skip condition
below) and runs each tests/rag_eval/golden_dataset.py question through
app/rag/orchestrator.py end-to-end, checking that at least one returned
citation points at the section a correct answer should be grounded in.

Requires:
  - A live, migrated Postgres instance (same as tests/integration/).
  - COPILOT_EMBEDDING_PROVIDER=openai with COPILOT_OPENAI_API_KEY set.
  - COPILOT_LLM_PROVIDER=anthropic with COPILOT_ANTHROPIC_API_KEY set.

The "fake" providers are deterministic but not semantically meaningful
(see their docstrings) — running this harness against them wouldn't test
anything about real retrieval quality or citation accuracy, so it's
skipped automatically rather than run against fakes. Run it explicitly:

    COPILOT_EMBEDDING_PROVIDER=openai COPILOT_OPENAI_API_KEY=... \
    COPILOT_LLM_PROVIDER=anthropic COPILOT_ANTHROPIC_API_KEY=... \
    pytest tests/rag_eval -v -m rag_eval

RECALL_THRESHOLD is deliberately below 1.0 (allowing up to one miss out
of six) — this harness exercises real, non-deterministic LLM/embedding
calls, so a small amount of slack is expected rather than brittle.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.data.session import SessionLocal
from app.ingestion.pipeline import run_ingestion
from app.rag.embedding_client import get_embedding_client
from app.rag.llm_client import get_llm_client
from app.rag.orchestrator import answer_question
from tests.rag_eval.golden_dataset import GOLDEN_DATASET

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"

_REAL_PROVIDERS_CONFIGURED = bool(
    settings.embedding_provider == "openai"
    and settings.openai_api_key
    and settings.llm_provider == "anthropic"
    and settings.anthropic_api_key
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.rag_eval,
    pytest.mark.skipif(
        not _REAL_PROVIDERS_CONFIGURED,
        reason="Requires real OPENAI_API_KEY + ANTHROPIC_API_KEY — the fake providers "
        "aren't semantically meaningful, see module docstring.",
    ),
]

RECALL_THRESHOLD = 0.8

SEED_DOCUMENTS = [
    {
        "filename": "centrifugal_pump_p101_sop.docx",
        "equipment_id": "P-101",
        "title": "Centrifugal Pump P-101 Maintenance SOP",
    },
    {
        "filename": "conveyor_cb200_manual.docx",
        "equipment_id": "CB-200",
        "title": "Conveyor Belt CB-200 Operations and Maintenance Manual",
    },
]


@pytest.fixture(scope="module")
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="module", autouse=True)
def _seed_documents(db_session: Session) -> Generator[None, None, None]:
    """Ingests the golden-dataset seed documents once for the whole
    module, using the real embedding provider — real API calls are
    expensive/slow enough that per-test ingestion would make this harness
    impractical to run.
    """
    embedding_client = get_embedding_client()
    document_ids = []
    for seed in SEED_DOCUMENTS:
        file_path = SEED_DIR / seed["filename"]
        document = Document(
            id=uuid4(),
            title=seed["title"],
            source_type="sop",
            equipment_id=seed["equipment_id"],
            plant_id=None,
            file_path=str(file_path),
            status="active",
            uploaded_by="rag-eval-harness",
        )
        db_session.add(document)
        db_session.flush()
        run_ingestion(
            db_session, document, file_path.read_bytes(), seed["filename"], embedding_client
        )
        document_ids.append(document.id)
    db_session.commit()

    yield

    db_session.query(Chunk).filter(Chunk.document_id.in_(document_ids)).delete(
        synchronize_session=False
    )
    db_session.query(Document).filter(Document.id.in_(document_ids)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_golden_dataset_citation_recall(db_session: Session) -> None:
    llm_client = get_llm_client()
    embedding_client = get_embedding_client()

    hits = 0
    misses: list[str] = []
    for case in GOLDEN_DATASET:
        result = answer_question(
            db_session,
            case.question,
            equipment_id=case.equipment_id,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
        matched = any(
            case.expected_section_contains in (c.section_title or "") for c in result.citations
        )
        if matched:
            hits += 1
        else:
            misses.append(case.question)

    recall = hits / len(GOLDEN_DATASET)
    assert recall >= RECALL_THRESHOLD, (
        f"Citation recall {recall:.2f} ({hits}/{len(GOLDEN_DATASET)}) is below the "
        f"{RECALL_THRESHOLD:.2f} threshold. Missed: {misses}"
    )

# Project Progress — `maintenance-copilot`

Living document, updated after every phase. Tracks what's actually built, what's
deliberately postponed (and why), architectural decisions made along the way, and what's
left. The Engineering Design Document (EDD) is the source of truth for *design*; this file
is the source of truth for *status*.

---

## Phase status

| Phase | Status |
|---|---|
| 1 — Foundation & Standalone Setup | ✅ Complete |
| 2 — Document Ingestion | ✅ Complete |
| 3 — RAG Core & Retrieval (stateless) | ⬜ Not started |
| 4 — Conversations & Persistence | ⬜ Not started |
| 5 — Feedback & Escalation | ⬜ Not started |
| 6 — Cross-Repo Integration, Agent Contract & Hardening | ⬜ Not started |

---

## Phase 1 — Foundation & Standalone Setup ✅

### Implemented

- Repo scaffolding matching the EDD's folder structure (§9): `app/api`, `app/config`,
  `app/data`, `alembic/`, `tests/unit`, `tests/integration`.
- Config: `app/config/settings.py`, Pydantic `BaseSettings`, all variables prefixed
  `COPILOT_`, `.env.example` provided.
- Structured JSON logging: `app/config/logging_config.py`.
- Database wiring: `app/data/base.py` (declarative `Base`), `app/data/session.py`
  (engine/session, `get_db` dependency).
- Auth hook stub: `app/api/deps.py::get_current_user()` — fixed identity today, swappable
  later without changing route signatures.
- `pgvector` extension enabled via baseline Alembic migration (`0001_enable_pgvector.py`).
  No application tables yet — those start in Phase 2.
- `/health` (liveness, no dependencies) and `/ready` (readiness, checks DB connectivity).
- Docker: `Dockerfile` (multi-stage, `uvicorn` entrypoint), `docker-compose.yml` (this
  repo's own `api` service only), `docker-compose.override.yml` (local Postgres+pgvector,
  for standalone runs — see "Architectural decisions" below).
- CI (`.github/workflows/ci.yml`): lint (`ruff`), format check (`black`), type check
  (`mypy`), migration run, tests — against a real Postgres service container, not mocked.
- Tests: `tests/unit/test_health.py` (no DB required), `tests/integration/test_ready.py`
  (requires a live, migrated Postgres — marked `@pytest.mark.integration`).

### Verified in this environment

`ruff check .`, `black --check .`, `mypy app`, and `pytest -v -m "not integration"` all
pass. Docker and a live Postgres instance were **not** available in the sandbox this was
built in, so `docker compose up` and the `/ready` + migration path were not exercised
end-to-end here — verify locally before treating Phase 1 as fully closed.

### Postponed (not part of Phase 1's scope)

Nothing was deferred *within* Phase 1 — everything the roadmap scoped to this phase is
implemented. See "Deliberately deferred, platform-wide" below for design-level deferrals
that span the whole project (from EDD §20), not phase-specific ones.

### Architectural decisions made during Phase 1

- **`docker-compose.yml` vs `docker-compose.override.yml` split, corrected mid-review.**
  Initial implementation had the base `api` service's `depends_on` pointing at a `postgres`
  service that only the override file defines — meaning the base file wasn't actually
  usable standalone (it referenced an undefined service), contradicting its own stated
  intent of staying generic for future platform-level composition. Fixed by moving the
  `depends_on` entry into `docker-compose.override.yml`, which Compose merges onto the
  `api` service already defined in the base file. Net effect: `docker-compose.yml` no
  longer assumes a service named `postgres` exists anywhere; the override file supplies
  both the service and the dependency on it. Verified the merge resolves correctly (see
  commit history / this file's review notes) since Docker wasn't available to test
  directly in the build environment.
- **`app/schemas/platform_contracts.py` intentionally not created yet.** Cheap to add, but
  nothing in Phase 1 reads or writes it, and the roadmap scopes it to Phase 6. Adding it
  now would be scaffolding ahead of the phase that needs it — the same anti-pattern the
  EDD's simplification pass (§20) was written to avoid.
- **`ruff`'s B008 rule ignored project-wide.** FastAPI's `Depends(...)`-as-default-argument
  is the framework's idiomatic dependency-injection pattern, not the mutable-default-arg
  bug that rule is designed to catch — every route in this repo uses it, so it's ignored
  in `pyproject.toml` rather than suppressed per-line.
- **Settings accessed via a cached function (`get_settings()`), not a bare module-level
  singleton.** Makes it possible to override configuration in tests later without
  monkeypatching a module attribute — a Phase 2+ concern, set up now while the settings
  module is still small.

---

## Phase 2 — Document Ingestion ✅

### Implemented

- **Schemas:** `app/schemas/document.py` — `DocumentCreateResponse`, `DocumentRead`. First
  schema module in the repo (Phase 1 deliberately didn't create one — nothing needed it yet).
- **Models:** `app/data/models/document.py`, `app/data/models/chunk.py`. `chunk.embedding`
  is a native `pgvector` `VECTOR(1536)` column on the same table as its text/metadata — one
  store, per EDD §11/§20.
- **Repositories:** `app/data/repositories/base.py` (generic `get`/`add` only — kept
  deliberately thin), `document_repository.py`, `chunk_repository.py`. Repositories never
  commit; the service layer owns transaction boundaries.
- **Ingestion pipeline** (`app/ingestion/`): `extractors.py` (PDF via `pypdf`, DOCX via
  `python-docx` — native text only, no OCR), `cleaning.py` (whitespace/hyphenation/page-number
  cleanup), `chunking.py` (structure-aware chunking: heading detection groups paragraphs
  under a `section_title`, ~500-token target with ~75-token overlap, oversized single
  paragraphs sentence-split), `pipeline.py` (ties extraction → cleaning → chunking →
  embedding → persistence into one function, used identically for upload and re-index).
- **Embedding client** (`app/rag/embedding_client.py`): `EmbeddingClient` interface,
  `OpenAIEmbeddingClient` (default real provider, `text-embedding-3-small`), and
  `FakeEmbeddingClient` (deterministic, hash-based, no network/API key — see "Architectural
  decisions" below).
- **Service:** `app/services/document_service.py` — `DocumentService` (create/get/list/
  reindex/archive/status transitions) plus `run_ingestion_job()`, a module-level function run
  as a FastAPI `BackgroundTask` with its own DB session, used identically by upload and
  by `POST /documents/{id}/reindex`.
- **Errors:** `app/services/errors.py` — `AppError` hierarchy (`NotFoundError`,
  `ValidationError`, `UnsupportedFileTypeError`) plus a FastAPI exception handler in
  `app/api/main.py` translating any `AppError` into the standard error envelope. First
  introduced now because document endpoints are the first to need domain errors.
- **Routes:** `POST /documents`, `GET /documents/{id}`, `GET /documents` (filterable by
  `equipment_id`/`plant_id`/`status`, paginated), `POST /documents/{id}/reindex`,
  `DELETE /documents/{id}` (soft archive).
- **Migration:** `0002_create_document_and_chunk_tables.py` — `document` and `chunk` tables,
  `ix_document_equipment_status`, `ix_chunk_document_id`, and an `ivfflat` cosine-similarity
  index on `chunk.embedding`.
- **Docker:** `docker-compose.yml` now bind-mounts `./data/raw:/app/data/raw` so uploaded
  source files persist across container restarts (chunk/embedding data lives in Postgres
  regardless, so this only affects re-index and inspection, not retrieval correctness).
- **Tests:** unit — `test_cleaning.py`, `test_chunking.py` (8 cases covering single/multi-chunk,
  heading detection, oversized-paragraph splitting, multi-page, DOCX no-page-number, empty
  input), `test_extractors.py` (in-memory generated PDF/DOCX fixtures via `fpdf2`/`python-docx`
  — no committed binary fixtures), `test_embedding_client.py`. Integration —
  `test_documents_api.py` (upload → ingest → chunks persisted, unsupported-type error
  envelope, not-found error envelope, equipment-filtered listing, re-index, archive), with a
  shared `conftest.py` providing a `db_session` fixture and automatic table cleanup between
  tests.

### Verified in this environment

`ruff`, `black --check`, `mypy`, and all 25 unit tests pass (`pytest -v -m "not integration"`).
The integration tests were **not** run — no live Postgres available in this sandbox, same
limitation noted in Phase 1. Verify locally with `docker compose up -d postgres && alembic
upgrade head && pytest -v -m integration` before treating Phase 2 as fully closed.

**Bug caught by actually running the tests, not just linting:** the `DELETE /documents/{id}`
route's `-> None` return annotation made FastAPI infer a response body was required, which
is invalid for a 204 status — this crashed route registration at import time, which would
have broken the entire app (including `/health`) at startup. Fixed with
`response_model=None`. Left in this log as a concrete example of why "lint clean" and
"type-checks clean" are not the same claim as "the app actually starts and passes its
tests" — all three were run before calling this phase done.

### Postponed (within Phase 2's own scope)

- **OCR.** Core scope is native text extraction (PDF/DOCX) only — see EDD §20. Seed
  documents for the standalone demo are chosen to be born-digital specifically so this
  isn't needed yet.
- **Exact tokenization (e.g. `tiktoken`).** `chunking.py` uses a cheap character-based
  token estimate instead. `tiktoken`'s BPE rank files are normally fetched from an external
  host on first use, which would make ingestion depend on network access to a domain
  outside this project's control — a hidden dependency this repo's NFR7 (no cloud-specific/
  hidden external dependencies) argues against. The estimate is swappable behind
  `estimate_token_count()` if precise token budgets become necessary later (e.g. approaching
  a provider's exact context-window limit).
- **Hybrid/keyword search and re-ranking.** Still documented extension points for
  `app/rag/retriever.py` in Phase 3, not built ahead of that phase.

### Architectural decisions made during Phase 2

- **`document.status` includes `'archived'`, which the EDD's original SQL literal (§11)
  didn't list even though the same section's API design explicitly specified a soft-delete
  `DELETE` endpoint.** This was a genuine inconsistency within the EDD itself, not a design
  choice to relitigate — resolved by adding `'archived'` to the status enum so the documented
  API behavior and the schema agree. No other status-lifecycle complexity (no `superseded`,
  no version history) was added — that remains deferred per §20.
- **`document.error_message` (nullable string) added beyond the EDD's original column list.**
  A single column capturing why ingestion failed, so a failed document is diagnosable from
  the API/DB directly without the dedicated `audit_log` table that's deferred (§20). Small,
  cheap, and directly supports NFR5 observability.
- **Fake embedding provider (`COPILOT_EMBEDDING_PROVIDER=fake`) is a first-class, documented
  configuration value, not test-only scaffolding.** `.env.example` and CI both default to it.
  This means `docker compose up` produces a fully working, self-consistent (if
  not semantically meaningful) ingestion+retrieval pipeline with zero external API keys —
  directly strengthens NFR1 (standalone runnability), not just a testing convenience. The
  code default in `settings.py` itself stays `"openai"` (the EDD's stated real-provider
  target) — only the example/CI defaults favor `"fake"`.
- **Background ingestion opens its own DB session (`SessionLocal()`), not the request's.**
  FastAPI keeps a request-scoped `yield` dependency alive until background tasks finish, so
  reusing the request's session would technically work — but making the background job's
  session lifetime independent and explicit is easier to reason about and doesn't couple a
  background job's correctness to a FastAPI implementation detail.
- **One ingestion code path, not two.** `run_ingestion_job()` is used identically by
  `POST /documents` (fresh upload) and `POST /documents/{id}/reindex` — chosen specifically
  to prevent the two flows from silently drifting apart, the same principle the EDD applies
  to `/conversations` vs `/agent` sharing one RAG orchestrator core in Phase 3+.
- **Repository `base.py` kept intentionally thin (`get`/`add` only).** `DocumentRepository`
  and `ChunkRepository` need almost nothing in common beyond fetch-by-id and
  add-to-session — forcing more shared surface into the base class than that would be
  premature abstraction for two concrete repositories.

---

## Deliberately deferred, platform-wide (from EDD §20)

Carried here for visibility — these are cross-cutting design decisions, not phase-specific
postponements, and stay accurate regardless of which phase is in progress.

| Deferred | Why not now | Trigger to revisit |
|---|---|---|
| Dedicated vector DB (Qdrant) | `pgvector` handles this data volume in one store | A second repo needs a shared vector store, or corpus size outgrows `pgvector` |
| Redis Streams event bus (consume + publish) | No consumer exists yet for a copilot-published event; a sync API call covers today's one real integration need | A second repo needs to react to copilot events asynchronously |
| Separately packaged `platform-data-contracts` / `platform-agent-sdk` | Two repos, one developer — packaging/versioning overhead exceeds the benefit | A third project consumes the same contract |
| Document version history | No need yet to pin citations to a specific historical document version | Multiple people manage the document set and need change history |
| OCR + human review queue | Seed corpus is curated to be born-digital | Real scanned legacy manuals enter the corpus |
| Scheduled reindex batch job | Document set doesn't change on a schedule | Ingestion volume outgrows synchronous/admin-triggered reindexing |
| Dedicated `audit_log` table | Structured logs already capture the same information | A compliance/reporting need requires querying audit history independently of logs |
| Escalation routing (`assigned_to`, `in_review` state) | One reviewer, one queue | A team, not a solo developer, is triaging escalations |

---

## Remaining work (by phase, per the roadmap in EDD §22)

- **Phase 3:** retriever, RAG orchestrator, prompt builder, LLM client, citation
  extraction, confidence scoring, no-answer fallback, stateless debug query endpoint,
  first golden-dataset evaluation.
- **Phase 4:** conversation/message/citation persistence, conversation memory, streamed
  `/conversations/{id}/messages`.
- **Phase 5:** feedback and escalation services, auto-escalation on low confidence.
- **Phase 6:** `/agent` endpoint, vendored `platform_contracts.py`, synchronous
  (non-blocking) risk-context enrichment call to `predictive-maintenance`, performance
  pass, README + `retrieval_card.md` finalized.

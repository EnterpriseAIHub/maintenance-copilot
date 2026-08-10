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
| 3 — RAG Core & Retrieval (stateless) | ✅ Complete |
| 4 — Conversations & Persistence | ✅ Complete |
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

**Update (Phase 3):** a local Postgres+pgvector instance was installed directly in the
build sandbox (see Phase 3's "Verified in this environment") and `tests/integration/
test_ready.py` was actually run for the first time — it passes. Phase 1 is now fully
verified, not just unit-tested.

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

**Update (Phase 3):** now verified — see Phase 3's "Verified in this environment". Running
`test_documents_api.py` against a real Postgres for the first time surfaced one real bug,
fixed as part of Phase 3 (see that section's bug note): unsupported file types were only
ever caught inside the async ingestion background job, so `POST /documents` always
returned `201` even for a file type ingestion could never process, instead of failing
synchronously with `400 UNSUPPORTED_FILE_TYPE`.

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

## Phase 3 — RAG Core & Retrieval (stateless) ✅

### Implemented

- **Retriever** (`app/rag/retriever.py`): pgvector cosine-similarity search
  (`Chunk.embedding.cosine_distance(...)`, matching the `ivfflat` index's
  `vector_cosine_ops` from migration `0002`) joined to `Document`, filtered to
  `status = 'active'` and optionally `equipment_id`/`plant_id` — filtered against
  `Document`'s own columns (indexed via `ix_document_equipment_status`), not the
  duplicate copy in `Chunk.chunk_metadata`. Returns `RetrievedChunk` (chunk + similarity).
- **LLM client** (`app/rag/llm_client.py`): `LLMClient` interface, `AnthropicLLMClient`
  (default real provider, Claude via the Messages API) and `FakeLLMClient` (deterministic,
  no network — same precedent as `FakeEmbeddingClient`). Citations are structured, not
  free-text: the model is forced (`tool_choice`) to call a single `provide_answer` tool
  whose schema requires `answer`, `cited_chunk_ids`, and a self-rated `confidence`.
- **Prompt builder** (`app/rag/prompt_builder.py`): system prompt instructing
  context-only, cited answers; user prompt assembling each retrieved chunk as a labeled
  block (`chunk_id`, `section`, `page`) followed by the question.
- **Citation extractor** (`app/rag/citation_extractor.py`): resolves the LLM's
  `cited_chunk_ids` back into `Citation` records (document, section, page, a short
  snippet) against the chunks that were actually retrieved — any cited id not in that set
  (a hallucinated citation) is dropped, not trusted.
- **Confidence scorer** (`app/rag/confidence_scorer.py`): `0.5 * mean similarity of cited
  chunks + 0.5 * LLM self-rated confidence`, clamped to `[0, 1]`. Zero citations → `0.0`
  outright, regardless of self-rating. Compared against `COPILOT_CONFIDENCE_THRESHOLD`
  by future callers (Phase 5's auto-escalation).
- **Orchestrator** (`app/rag/orchestrator.py`): `answer_question()` — the single function
  chaining retrieval → prompt → LLM call → citation extraction → confidence scoring.
  Accepts optional `embedding_client`/`llm_client` overrides (used by tests and the eval
  harness); defaults to whatever `app/config/settings.py` configures. Returns a `RagAnswer`
  (answer, citations, confidence, retrieved_chunk_count), or a fixed "no ingested
  documents address this" answer with `confidence=0.0` when retrieval returns nothing.
  Intended to be the same function `/conversations/{id}/messages` (Phase 4) and `/agent`
  (Phase 6) call later, unchanged — same "one code path" principle already used for
  `run_ingestion_job()` in Phase 2.
- **Schemas & route:** `app/schemas/query.py` (`QueryRequest`, `QueryResponse`,
  `CitationRead`), `app/api/routes/query.py` — `POST /query`, a stateless debug/eval
  endpoint (no conversation persistence — that's Phase 4). Empty/whitespace-only
  `question` raises `ValidationError` synchronously (same `AppError` envelope as every
  other domain error in this repo), rather than relying on Pydantic's own 422 shape.
- **Config:** `Settings` gained `llm_provider` (already present, now actually read),
  `anthropic_api_key`, `llm_model` (default `claude-sonnet-5`), and `retrieval_top_k`
  (default `5`) — added alongside the first code that reads each, per the existing rule.
  `.env.example` and CI now default `COPILOT_LLM_PROVIDER=fake` in addition to
  `COPILOT_EMBEDDING_PROVIDER=fake`, so `docker compose up` still requires zero external
  API keys (NFR1) now that a second real provider exists.
- **Dependency:** `anthropic` SDK added to `requirements.txt` (also deduplicated a stray
  repeated block in that file left over from an earlier edit — `python-multipart`/`pypdf`/
  `python-docx`/`openai` were each listed twice; harmless but untidy).
- **Golden-dataset evaluation harness** (Phase 3's exit criterion):
  `scripts/generate_seed_docs.py` generates two synthetic, born-digital seed documents
  (`data/seed/centrifugal_pump_p101_sop.docx`, `data/seed/conveyor_cb200_manual.docx` — a
  pump maintenance SOP and a conveyor manual, five sections each, ALL-CAPS headings sized
  so each section lands in its own chunk under the default ~500-token target — see that
  script's docstring for why ALL CAPS specifically). `tests/rag_eval/golden_dataset.py`
  pairs six questions (three per document) with the section a correct, grounded answer
  should cite. `tests/rag_eval/test_golden_eval.py` ingests both seed documents once per
  module run and asserts citation recall ≥ 0.8 across the six questions — but only against
  the **real** embedding/LLM providers (`COPILOT_EMBEDDING_PROVIDER=openai` +
  `COPILOT_LLM_PROVIDER=anthropic` with both API keys set); it self-skips otherwise via
  `pytest.mark.skipif`, since the fake providers aren't semantically meaningful and running
  a recall eval against them wouldn't test anything real. New `rag_eval` pytest marker.
- **Tests:** unit — `test_llm_client.py`, `test_prompt_builder.py`,
  `test_citation_extractor.py`, `test_confidence_scorer.py` (23 cases total). Integration
  — `test_retriever.py` (6 cases: exact-match ordering, equipment/plant filtering, active-
  only filtering, top_k, no-match), `test_orchestrator.py` (3 cases, using
  `FakeEmbeddingClient`+`FakeLLMClient` against a real DB), `test_query_api.py` (4 cases,
  full HTTP round-trip through real `/documents` upload then `/query`).

### Verified in this environment

Unlike Phases 1–2, this phase's verification wasn't deferred: Docker itself still isn't
available in this build sandbox, but a local **Postgres 16 + pgvector** instance was
installed directly (`apt-get install postgresql postgresql-16-pgvector`, both packages
resolve via the sandbox's allowed apt mirrors) and migrations were run against it with
`alembic upgrade head`. With that in place, **every** test in the repo — Phase 1–2's
previously-unexecuted integration tests included — was actually run and passes:
`ruff check .`, `black --check .`, `mypy app` all clean; `pytest -v` (full suite, run once,
justified because this phase touched shared infrastructure — `chunking.py` and
`document_service.py`, both Phase 2 files, see bug note below) → **70 passed, 1 skipped**
(the golden-dataset eval, correctly self-skipping — no real provider keys in this
sandbox). The golden-dataset harness itself could not be run end-to-end here since no real
`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` were available in this sandbox; it needs local
verification with real keys before the Phase 3 exit criterion is fully closed.

**Two real bugs found and fixed as a direct result of finally running these tests:**

1. **Chunking mislabeled `section_title` when short sections got merged into one chunk**
   (`app/ingestion/chunking.py`). `flush()` labeled a chunk using `current_section` — the
   *most recently seen* heading at flush time — rather than the heading in effect when
   that chunk's content actually started accumulating. Two short adjacent sections that
   together still fit under `target_tokens` would end up in one chunk mislabeled with the
   *second* section's heading, even though most (or all) of the chunk's content belonged
   to the first. Found while building the golden-dataset seed documents (the conveyor
   document's `OVERVIEW` + `BELT TENSIONING` merged this way) — this would have silently
   produced wrong citations. Fixed by tracking a separate `buffer_section` that's only
   updated when the buffer is empty (i.e., at the start of new content), and using that at
   flush time instead of the live `current_section`. Regression tests added:
   `test_merged_chunk_keeps_first_sections_heading_not_a_later_one`,
   `test_section_boundary_forces_correct_label_on_each_side`.
2. **`POST /documents` never synchronously rejected unsupported file types**
   (`app/services/document_service.py`). The extension check only ever ran inside
   `run_ingestion_job()` — the async background task — so upload always returned `201`
   even for a file type ingestion could never process; the `400 UNSUPPORTED_FILE_TYPE`
   response only ever existed in `tests/integration/test_documents_api.py`'s *expectation*,
   never in the actual code path, because that test had never been executed against a real
   Postgres before this phase. Fixed by checking `Path(filename).suffix` against
   `SUPPORTED_EXTENSIONS` synchronously in `DocumentService.create_document()`, before any
   DB row or file is written — fail fast on a bad request rather than deferring the
   failure to a background job. This is a Phase 2 bug, fixed now because verifying Phase
   1–2's deferred integration tests before starting Phase 3's retriever work (per this
   file's own prior "Where Phase 3 should begin" note) is what surfaced it.

### Postponed (within Phase 3's own scope)

- **`/ready` does not call the LLM/embedding provider.** Considered adding a provider
  reachability check now that both clients exist, but readiness probes run frequently and
  turning each one into a paid external API call is a cost/rate-limit risk for no real
  benefit — provider failures already surface per-request as a normal error response from
  `POST /query`. Documented directly in `app/api/routes/health.py`'s docstring.
- **Hybrid/keyword search and re-ranking.** Still documented extension points for
  `retriever.py`, not built without a concrete accuracy problem to justify them (per Phase
  2's own note carrying this forward).

### Architectural decisions made during Phase 3

- **Citations are structured (tool-forced), not parsed from free text.** The LLM must call
  a single `provide_answer` tool (`tool_choice` forced) whose schema requires
  `cited_chunk_ids` and a self-rated `confidence` alongside the answer — chosen over
  asking for prose and reverse-engineering which chunks it used, since that avoids ever
  matching a citation to the wrong chunk because of similar wording. Confirmed and
  finalized with the user before implementation (this and the two decisions below were
  explicitly asked about, since the roadmap didn't pin them down).
- **Confidence = 0.5 × mean similarity of *cited* chunks + 0.5 × LLM self-rated
  confidence**, not either signal alone. Retrieval similarity alone says nothing about
  whether the model used the evidence correctly; an LLM's self-rating alone is well known
  to be poorly calibrated. Zero citations forces `0.0` regardless of self-rating, since an
  ungrounded self-rating isn't evidence of anything.
- **Golden-dataset seed content is synthetic, generated by this repo** (`scripts/
  generate_seed_docs.py`), not supplied external documents — confirmed with the user.
  Body paragraph lengths were deliberately tuned (via a dry run of the actual chunking
  output, not guessed) so each section lands in its own chunk, since the eval's citation-
  recall assertions depend on that.
- **Retriever filters `equipment_id`/`plant_id` against `Document`'s own columns**, not
  the duplicate copy written into `Chunk.chunk_metadata` at ingestion time. Same effective
  filter, but reuses the existing `ix_document_equipment_status` index and avoids a JSONB
  text-extraction comparator for no benefit.
- **`FakeLLMClient` cites every `chunk_id` it's given** (passed explicitly as a parameter
  to `generate_answer()`, alongside the prompt) rather than parsing ids back out of the
  prompt text it was handed. Simpler and more robust than regex-extracting from its own
  input, and keeps `AnthropicLLMClient` and `FakeLLMClient` behind the exact same
  interface.
- **Golden-dataset harness (`tests/rag_eval/`) is a new pytest marker, self-skipping
  without real provider keys**, rather than being excluded by convention (like
  `-m "not integration"`) or requiring a separate invocation the CI workflow has to
  remember. `pytest -v` (no marker filter, matching CI) runs it, sees no real keys
  configured, and skips — so it can never silently rot out of the test run entirely, but
  also never fails CI for lacking paid API credentials.
- **`requirements.txt` deduplicated** while adding `anthropic` — a stray repeated block
  (`python-multipart`, `pypdf`, `python-docx`, `openai` each listed twice) was cleaned up
  in the same edit since it was directly in the file being touched; not a separate
  unscoped change.

---

## Phase 4 — Conversations & Persistence ✅

### Implemented

- **Schema (migration `0003`):** `conversation` (id, equipment_id/plant_id, started_by,
  timestamps — same optional-scoping pattern as `document`), `message` (id,
  conversation_id FK CASCADE, `role` CHECK IN `('user','assistant')`, content, confidence
  and retrieved_chunk_count nullable/assistant-only), `citation` (id, message_id FK
  CASCADE, `chunk_id`/`document_id` FK **SET NULL** — deliberately not CASCADE, so a
  citation survives a later document reindex that deletes the chunk it pointed at — plus
  denormalized `section_title`/`page_number`/`snippet` copied at write time, same
  reasoning as Phase 2's `document.error_message`). New models registered in
  `alembic/env.py` for autogenerate, matching Phase 2's precedent. Both `alembic upgrade
  head` and `alembic downgrade -1` verified against a live Postgres.
- **Repositories:** `conversation_repository.py`, `message_repository.py` (adds
  `list_by_conversation` for full history and `list_recent_by_conversation` for bounded
  history-loading), `citation_repository.py` (adds `create_many`, mirroring
  `chunk_repository.py`'s bulk-insert pattern). No commits in any of them — same rule as
  every other repository in this repo.
- **Orchestrator/prompt builder — additive only, as agreed with the user before
  implementation:** `app/rag/prompt_builder.py` gained `ConversationTurn` (question,
  answer) and an optional `conversation_history` parameter on `build_prompt()`, rendered
  as a "Conversation so far" block *before* the `Context:` block, and the system prompt
  now explicitly tells the model history is for understanding follow-ups, not a citable
  source. `app/rag/orchestrator.py::answer_question()` gained the same optional parameter,
  threaded straight through to `build_prompt()`. **Retrieval embedding still comes from
  `question` alone in every case** — history never reaches `embedding_client.embed()`.
  Verified additive, not just by inspection: every Phase 3 test (36 cases across
  `test_prompt_builder.py`, `test_llm_client.py`, `test_citation_extractor.py`,
  `test_confidence_scorer.py`, `test_orchestrator.py`, `test_query_api.py`,
  `test_retriever.py`) was re-run immediately after this change and passed unchanged, plus
  a new regression test (`test_no_conversation_history_produces_identical_prompt_to_
  omitting_it`) asserts the `conversation_history=None` default produces a byte-for-byte
  identical prompt to calling `build_prompt()` without the parameter at all.
- **`ConversationService`** (`app/services/conversation_service.py`): owns conversation
  state the way `DocumentService` owns document state.
  - `create_conversation()` / `get_conversation()` (raises `NotFoundError`) /
    `list_messages()` (full history, oldest-first, each message's citations attached).
  - `generate_answer_stream()` — a plain synchronous generator: persists the user message
    and commits immediately (so it's saved even if the LLM call that follows fails or the
    client disconnects mid-stream), yields a `retrieving` event, loads bounded
    conversation history, yields a `generating` event, calls `answer_question()`
    (wrapped in a broad `try/except` — by this point a 200 response has already started,
    so a pipeline failure becomes a clean `error` SSE event rather than a raw traceback),
    persists the assistant message + citation rows and commits, then yields a `done` event
    carrying the full `MessageRead` (answer, confidence, citations).
  - `_load_conversation_history()` pairs up the most recent user/assistant messages into
    `ConversationTurn`s, bounded by the new `COPILOT_CONVERSATION_HISTORY_LIMIT` (default
    6 turns) — over-fetches by one extra pair specifically to account for the
    just-committed, not-yet-answered current question, which naturally drops out of the
    pairing as a dangling unmatched "question" rather than needing an explicit filter.
- **Schemas** (`app/schemas/conversation.py`): `ConversationCreateRequest`,
  `ConversationRead`, `MessageCreateRequest`, `MessageRead`, and a `CitationRead` that is
  **deliberately its own type**, not a reuse of Phase 3's `app/schemas/query.py::
  CitationRead` — a persisted citation's `chunk_id`/`document_id` are nullable (the
  `SET NULL` FK above), while Phase 3's in-flight version correctly has both non-nullable;
  reusing the Phase 3 type here would either lie about nullability or loosen a type Phase
  3 already got right for its own use case.
- **Routes** (`app/api/routes/conversations.py`, prefix `/conversations`):
  - `POST /conversations` → 201, creates a conversation.
  - `GET /conversations/{id}` → 404 via the standard `AppError` envelope if unknown.
  - `GET /conversations/{id}/messages` → full history with citations; 404 first if the
    conversation doesn't exist.
  - `POST /conversations/{id}/messages` → **SSE** (`text/event-stream`), emitting
    `retrieving` → `generating` → `done` (or `error`) — see "Streaming decision" below.
    Conversation-not-found and empty-question validation happen *before* the
    `StreamingResponse` is constructed, so those two failures still go through the normal
    JSON `AppError` envelope (status/headers aren't committed yet at that point); only a
    failure *during* the RAG pipeline itself becomes an `error` SSE event, since a 200 has
    already started streaming by then.
  - Registered in `app/api/main.py` alongside `health`, `documents`, `query`.
- **Config:** `Settings.conversation_history_limit: int = 6`, added alongside the first
  code that reads it (`ConversationService._load_conversation_history`), per the existing
  rule.
- **Test fixture change:** `tests/integration/conftest.py`'s autouse cleanup fixture
  (renamed `_clean_document_tables` → `_clean_tables`, since its scope grew) now also
  deletes `Conversation` rows between tests — `message`/`citation` cascade automatically
  via the real DB-level `ON DELETE CASCADE` from migration 0003, no separate queries
  needed. This is shared test infrastructure touching every integration test file, so the
  **full suite was re-run once** after this change (see "Verified in this environment").
- **Tests:** `tests/integration/test_conversation_service.py` (6 cases — creation, 404,
  full persist-both-turns-and-citations round trip, no-evidence case, conversation history
  actually reaching the second call via a monkeypatched spy on `answer_question`, and the
  history-limit cap verified directly against `_load_conversation_history`);
  `tests/integration/test_conversations_api.py` (8 cases — full HTTP round trip through
  real `/documents` upload → `/conversations` → SSE `/conversations/{id}/messages`,
  parsing the actual `event: ...\ndata: ...\n\n` text the route writes, plus `GET
  /conversations/{id}/messages`, and both 404/422 error paths); 4 new unit tests in
  `test_prompt_builder.py` for the history-rendering behavior.

### Verified in this environment

Same local Postgres 16 + pgvector instance from Phase 3 (still no Docker in this
sandbox). Migration `0003` was applied and **also downgraded and re-applied** to confirm
both directions work, not just `upgrade`. `ruff check .`, `black --check .`, `mypy app`
all clean (49 source files). Every new integration test — 6 in
`test_conversation_service.py`, 8 in `test_conversations_api.py` — passes against the live
DB, including real SSE bodies parsed back out of an actual HTTP response, not simulated.
Because this phase's one shared-infrastructure change (`conftest.py`'s autouse fixture)
affects every integration test file, the **full suite was run once**: `pytest -v` →
**89 passed, 1 skipped** (the golden eval, still correctly self-skipping — no real
provider keys in this sandbox, unchanged from Phase 3).

No bugs were found in previously-untested Phase 1–3 code paths this phase — Phase 3's
verification pass already exercised the shared infrastructure this phase builds on
(migrations, repositories, retriever, orchestrator), so there wasn't a large surface of
never-executed code left for this phase to newly surface problems in.

### Streaming decision (recap of what was agreed before implementation)

Phase 3's citation strategy forces a tool call (`provide_answer`) whose answer text is a
field inside a JSON object, not free-flowing text — real token-by-token streaming of just
that field would mean incrementally parsing partial JSON mid-stream, real added complexity
for a citation architecture Phase 3 already spent a design decision getting right. Per
direction from the user: `POST /conversations/{id}/messages` streams SSE **progress
events** (`retrieving` → `generating` → `done`), not token-by-token text, and Phase 3's
tool-forced citation architecture is preserved exactly as built — `answer_question()` is
called the same way `/query` calls it, just with `conversation_history` added.
Token-level streaming is not implemented this phase.

### Postponed (within Phase 4's own scope)

- **Token-by-token answer streaming.** See "Streaming decision" above — explicit scope
  decision, not an oversight. Revisit only if the citation architecture itself changes
  (e.g. inline citation markers in free-flowing text) or if the SSE progress-event UX
  proves insufficient for a real frontend.
- **Conversation title/status.** Nothing in this phase's scope reads either; adding them
  now would be scaffolding ahead of need. Revisit if Phase 5+ needs to list/label
  conversations for a reviewer queue.

### Architectural decisions made during Phase 4

- **`conversation_history` is additive-only on `answer_question()`/`build_prompt()`**,
  confirmed with the user before implementation specifically because it touches
  Phase-3-complete files. Retrieval semantics are untouched — the embedding call still
  only ever sees the current `question` string; history is prompt-context only. This was
  verified, not just designed: the full Phase 3 test suite was re-run immediately after
  the change and a new "identical prompt when omitted" regression test was added.
- **Citation persistence denormalizes rather than relies on live joins.** Same reasoning
  extended from Phase 2's `document.error_message`: a citation's `section_title`/
  `page_number`/`snippet` are copied at write time, and `chunk_id`/`document_id` use
  `ON DELETE SET NULL` rather than `CASCADE`, so a conversation's citation history stays
  readable independent of the source chunk's own lifecycle (which is expected to churn —
  reindexing deletes and replaces chunks).
- **`CitationRead` for persisted citations is a distinct type from Phase 3's `CitationRead`
  in `app/schemas/query.py`**, not a shared/reused one, specifically because their
  nullability differs for a real reason (see "Implemented" above) — reuse would have been
  DRY for its own sake at the cost of an inaccurate type.
- **Per-step commits within `generate_answer_stream()`, not one transaction for the whole
  turn** — consistent with `run_ingestion`'s existing precedent (see PROJECT_PROGRESS.md's
  "Known limitations" from Phase 2), but the practical reason is stronger here: an SSE
  client can disconnect mid-stream, and the user's own question should still be saved even
  if the LLM call after it fails or the connection drops.
- **`conftest.py`'s autouse cleanup fixture renamed** (`_clean_document_tables` →
  `_clean_tables`) in the same edit that widened its scope to conversation tables — not a
  separate unscoped rename, done because leaving a name that no longer describes what the
  fixture does would be its own small inaccuracy left for the next phase to trip over.

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

- **Phase 5:** feedback and escalation services, auto-escalation on low confidence (using
  `COPILOT_CONFIDENCE_THRESHOLD` against the score `app/rag/confidence_scorer.py` already
  produces — every persisted assistant `message` row already carries `confidence`, so
  Phase 5's escalation trigger can read it directly without new plumbing).
- **Phase 6:** `/agent` endpoint, vendored `platform_contracts.py`, synchronous
  (non-blocking) risk-context enrichment call to `predictive-maintenance`, performance
  pass, README + `retrieval_card.md` finalized.

### Before starting Phase 5

The golden-dataset harness (`tests/rag_eval/test_golden_eval.py`) still needs to be run
locally with real `COPILOT_OPENAI_API_KEY` + `COPILOT_ANTHROPIC_API_KEY` at least once —
it has self-skipped in this sandbox every phase so far for lack of those keys, so Phase
3's actual citation-recall exit criterion (≥ 0.8 across the six golden questions) has
still not been checked against real model output. Run:

```bash
COPILOT_EMBEDDING_PROVIDER=openai COPILOT_OPENAI_API_KEY=... \
COPILOT_LLM_PROVIDER=anthropic COPILOT_ANTHROPIC_API_KEY=... \
pytest tests/rag_eval -v -m rag_eval
```

If recall comes in below 0.8, the likely places to look first are `app/rag/
prompt_builder.py`'s system prompt wording and whether the seed documents' chunk
boundaries still land where `scripts/generate_seed_docs.py`'s docstring expects (re-run
the chunking dry run shown in that script's docstring before assuming the prompt is at
fault).

Also worth a real (non-fake-provider) manual smoke test before Phase 5: open two browser
tabs or two `curl --no-buffer` sessions against `POST /conversations/{id}/messages` for
the *same* conversation back-to-back, and confirm the second answer's prompt actually
used the first turn as context (e.g. ask "how often should P-101's bearing be lubricated"
then "what about the seal instead" and confirm the second answer correctly resolves "the
seal" to P-101 without it being restated). This was verified against the fake LLM client
(which can't demonstrate real contextual understanding, only that history reaches the
prompt), not yet against a real model.

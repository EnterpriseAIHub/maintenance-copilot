# maintenance-copilot

RAG-based maintenance knowledge copilot — **Project A** of the Enterprise AI Platform.

Given a maintenance-related question (optionally scoped to a piece of equipment), retrieves
relevant evidence from ingested manuals/SOPs/work-order history and returns a grounded,
cited, confidence-scored answer. Where `predictive-maintenance` answers "will this fail,
and when," this repo answers "what do we know about this, and where did that come from."

Full design rationale, including what's deliberately deferred and why, lives in the
Engineering Design Document (not included in this repo checkout — see the project's
planning artifacts).

## Status

**Project — complete.** Documents can be uploaded, extracted, cleaned, chunked,
embedded, and stored. Questions can be answered with grounded, cited, confidence-scored
responses via a stateless `POST /query` debug endpoint, or as a persisted, streamed
conversation via `POST /conversations/{id}/messages`, with prior turns feeding
conversation memory. Technicians can leave helpful/not-helpful feedback on an answer, and
low-confidence or negative-feedback answers are auto-escalated to a reviewer queue
(`GET /escalations`). `POST /agent` exposes this repo as a pure data provider for a future
platform orchestrator (EDD §12's exact contract shape, no cross-repo calls of its own).
Conversations scoped to an `equipment_id` get an optional, non-blocking risk-context
enrichment from `predictive-maintenance` that degrades gracefully when that repo is absent
or unreachable — this repo remains fully standalone-runnable either way (NFR1). All 6
roadmap phases are implemented; what remains is real-environment verification (real
provider API keys, a real `predictive-maintenance` instance, Docker) that hasn't been
possible in the sandbox this was built in — see `PROJECT_PROGRESS.md`'s "Remaining work"
for the specific, unresolved list. See `PROJECT_PROGRESS.md` for full phase-by-phase
status, what's deliberately deferred, and architectural decisions made along the way.

## Running standalone

This repo runs with zero other Enterprise AI Platform repos present (NFR1):

```bash
cp .env.example .env
docker compose up
```

This starts a local Postgres instance (with the `pgvector` extension enabled) via
`docker-compose.override.yml`, runs migrations, and serves the API at `http://localhost:8000`.

Check it's alive:

```bash
curl http://localhost:8000/health   # process is up
curl http://localhost:8000/ready    # process can reach the database
```

Upload a document (works out of the box with no API key — `.env.example` defaults to the
`fake` embedding provider; see "Architecture notes" below):

```bash
curl -X POST http://localhost:8000/documents \
  -F "title=Pump Manual" \
  -F "source_type=manual" \
  -F "equipment_id=EQ-4471" \
  -F "file=@/path/to/manual.pdf"
# -> {"document_id": "...", "status": "processing"}

curl http://localhost:8000/documents/<document_id>
# -> status becomes "active" once ingestion (extract/clean/chunk/embed) completes
```

## Running locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt

docker compose up -d postgres   # just the database
alembic upgrade head
uvicorn app.api.main:app --reload
```

## Tests

```bash
pytest -v                      # unit tests only need no external services
pytest -v -m integration       # requires a running, migrated Postgres instance
```

## Architecture notes for future phases / future platform integration

- **Ownership:** this repo owns `document`, `chunk`, `conversation`, `message`, `citation`,
  `feedback`, `escalation` — added across Phases 2–5. It never writes to another repo's
  data (`Equipment`, `WorkOrder`); those are read via API only, never direct DB access.
- **One data store:** Postgres + the `pgvector` extension hold both relational data and
  chunk embeddings — no separate vector database service. See the EDD's "Deliberately
  Deferred" section for why, and what would change that.
- **Config:** all environment variables are prefixed `COPILOT_` (see `.env.example`) so
  this repo can be composed alongside sibling repos without collisions.
- **Embedding provider:** `COPILOT_EMBEDDING_PROVIDER` is `gemini` (real, default
  demo provider, needs `COPILOT_GEMINI_API_KEY`), `openai` (real, kept available for
  future use — needs `COPILOT_OPENAI_API_KEY`), or `fake` (deterministic, no key/network
  needed — `.env.example` defaults to this so the repo runs fully standalone out of the
  box). Retrieval quality with `fake` isn't meaningful; it exists to prove the
  ingestion/storage plumbing works, not as a real offline embedding model.
- **LLM provider:** `COPILOT_LLM_PROVIDER` is `groq` (real, default demo provider, needs
  `COPILOT_GROQ_API_KEY`), `gemini` (real, needs `COPILOT_GEMINI_API_KEY` — shared with
  the embedding provider above), `openai` (real, kept available for future use — needs
  `COPILOT_OPENAI_API_KEY`), or `fake` (deterministic, no key/network needed — also
  defaulted to in `.env.example`, for the same standalone-runnability reason as the
  embedding provider above). Anthropic support has been removed entirely — see
  `PROJECT_PROGRESS.md`'s "Provider migration" section.
- **Cross-repo integration (Phase 6):** `POST /agent` (`app/schemas/
  platform_contracts.py`) exposes this repo as a data *provider* for a future platform
  orchestrator, matching EDD §12's contract exactly, with **no cross-repo calls of its
  own** — it is not a composer/consumer of other repos' data, and never will be; see
  `PROJECT_PROGRESS.md`'s architectural review notes for why that boundary matters. The
  one cross-repo call this repo makes lives on `/conversations/{id}/messages` instead (an
  optional, non-blocking `GET /equipment/{id}/risk` enrichment from
  `predictive-maintenance`, attempted only when the conversation has an `equipment_id`,
  bounded by `COPILOT_PREDICTIVE_MAINTENANCE_TIMEOUT_SECONDS`) — degrades gracefully to
  "omitted" on any failure and is skipped entirely when
  `COPILOT_PREDICTIVE_MAINTENANCE_BASE_URL` is unset — the default, and what keeps this
  repo standalone-runnable (NFR1) regardless of whether any sibling repo is present.
- **`docker-compose.yml` vs `docker-compose.override.yml`:** the base file defines this
  repo's own `api` service only; the override file supplies a local Postgres so the repo
  runs standalone by default. A future platform-level compose (multiple repos sharing one
  Postgres instance) only needs to omit the override — `docker-compose.yml` itself doesn't
  change.

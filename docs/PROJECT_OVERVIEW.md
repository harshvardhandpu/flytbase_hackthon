# ScoutOS: project overview

ScoutOS is a multi-agent BDR operating system for discovering, researching, qualifying, and engaging prospects. A user defines a goal; specialised agents execute bounded tasks; a human approves material external actions.

## Phase 1 scope

- FastAPI application skeleton with health endpoint
- Provider-neutral AI and memory contracts
- Agent/task contracts and dependency boundaries
- PostgreSQL domain schema and Alembic migration
- Configuration and contributor guidance

Not in Phase 1: scraping, CRM integrations, asynchronous workers, vector search, live LLM calls, authentication, UI, or autonomous sending.

## Operating model

`Mission -> agent task -> agent result/log -> human review when required -> downstream task`

The persistent task and log records provide traceability. Agent outputs are stored as structured JSON until a later phase defines stricter result schemas.

Read [ARCHITECTURE.md](ARCHITECTURE.md), then [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md).

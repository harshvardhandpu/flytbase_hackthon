# Development guide

## Prerequisites

Python 3.12 and PostgreSQL 16 are recommended. Redis is optional until a worker is implemented.

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

Check `GET /health`. Run `pytest` and `ruff check .` before handing off changes.

## Manual inbound simulation

For local demos without a mailbox:

1. Seed demo data: `python scripts/seed_demo_data.py` (or use `/demo`).
2. Open `/inbound/new` (or click **New Inbound Email** on `/inbound`).
3. Optionally click **Fill SkyGrid demo**, then **Analyze Incoming Email**.
4. The app creates/links contact+lead records, runs Inbound → Qualification → Pipeline agents, and redirects to `/inbound/analysis/{task_id}`.

API endpoints: `POST /api/v1/inbound/simulate`, `GET /api/v1/inbound/{task_id}/simulation`.

## Coding rules

- Keep HTTP handlers thin; place use cases in `application/` when they appear.
- Depend on contracts in `core`, never a concrete AI provider from an agent.
- Add a migration for every model/schema change.
- Use typed Pydantic/SQLAlchemy models and UTC timestamps.
- Record meaningful task events without secrets or raw private data.
- Update the relevant documentation in the same change.

## Deliberately deferred

Do not introduce LangGraph, CrewAI, a vector database, web scraping, an LLM SDK, CRM APIs, auth, a frontend framework, Docker, or automatic message sending unless the phase explicitly requires it.

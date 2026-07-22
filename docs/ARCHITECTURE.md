# Architecture

## Stack choice

Use Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, and Redis (later). FastAPI is compact, typed, async-friendly, and lets a hackathon team add API endpoints and agent workers quickly. PostgreSQL holds operational truth; Redis is reserved for task dispatch/caching, not business data.

## Bounded layers

```text
api/            HTTP transport only
application/    use cases and orchestration (future)
agents/         specialised agent implementations
core/           contracts, runtime, task/memory/tool managers
providers/      provider adapters behind AIProvider
memory/         knowledge-retrieval contracts
db/             SQLAlchemy models, session, migrations
```

Dependencies point inward: API and agents depend on `core` contracts; provider adapters implement contracts; models never call providers or agents. Agents must not import a concrete provider.

## Runtime flow

1. API or worker creates an `AgentTask`.
2. `AgentRuntime` resolves an agent and gives it an `AgentContext`.
3. The agent uses only injected AI, memory, and tool contracts.
4. `TaskManager` records status; `AgentLog` records significant events.
5. Actions marked `requires_human_approval` stop at a review boundary.

The initial runtime is intentionally a contract, not an orchestrator. Replace or adapt it for LangGraph, CrewAI, or a custom queue without changing agent interfaces.

## Deployment boundary

The API process is stateless. PostgreSQL is required. Redis becomes required only when a background dispatcher is added. Provider credentials remain environment variables and never enter database logs.

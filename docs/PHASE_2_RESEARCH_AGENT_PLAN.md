# Phase 2 — Research Agent Implementation Plan

## 1. Goal

Make `ResearchAgent` real. A user provides a company name or domain; the agent gathers structured intelligence via web research, synthesizes findings into a cited `ResearchReport`, persists everything to PostgreSQL, and surfaces results through REST endpoints.

---

## 2. What Already Exists (Phase 1)

| Component | Status | File |
|-----------|--------|------|
| `ResearchAgent` class | Skeleton — raises `NotImplementedError` | `app/agents/research.py` |
| `ResearchReport` model | Fully typed with company, task, sources, provider | `app/db/models.py` |
| `AgentTask` model | Full lifecycle model (pending → running → completed/failed) | `app/db/models.py` |
| `AgentLog` model | Audit event model with level, event_type, data | `app/db/models.py` |
| `AIProvider` contract | `generate(request) -> AIResponse` | `app/core/contracts.py` |
| `AgentTool` contract | `execute(payload) -> ToolResult` (content + sources) | `app/core/contracts.py` |
| `ToolManager` | `execute(name, payload) -> ToolResult` | `app/core/tool_manager.py` |
| `TaskManager` | Stub — `mark_running`, `mark_completed`, `mark_failed` all raise `NotImplementedError` | `app/core/task_manager.py` |
| `AgentRuntime` | Resolves agent by type, calls `run()` | `app/core/agent_runtime.py` |
| Provider adapters | All 4 adapters exist but every `generate()` raises `NotImplementedError` | `app/providers/*.py` |
| `InMemoryAgentRegistry` | Builds registry from agent list | `app/agents/registry.py` |

---

## 3. What Must Be Built

### 3.1 Implement at least one AI Provider adapter

**Why:** The Research Agent needs to call an LLM to plan queries, synthesize findings, and structure output. Without a working `generate()`, no agent can function.

**Approach:** Implement the Anthropic provider adapter first since it's the primary target (and `freemodel` inherits from it). The adapter will use `httpx` (already a FastAPI dependency) to make HTTP requests to the Anthropic Messages API.

**Details:**
- `AnthropicProvider.generate()` makes a POST to `{base_url}/v1/messages`
- Reads settings (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL`) from config
- Maps `AIRequest.messages` → Anthropic message format
- Extracts `content`, `model`, `usage` from the response
- Errors raise a custom `ProviderError` so agents can catch them gracefully
- `OpenAIProvider` can be implemented similarly for the OpenAI-compatible path
- No SDK dependency — plain `httpx` to keep it lightweight

**Files to touch:**
- `app/providers/anthropic.py` — implement `generate()`
- `app/providers/openai.py` — implement `generate()` (secondary)
- `app/config.py` — no changes needed (settings already exist)
- `app/core/contracts.py` — add `ProviderError` exception class

### 3.2 Implement TaskManager

**Why:** The current `TaskManager` is a stub. The Research Agent must record task lifecycle events and log entries.

**Approach:** Implement `TaskManager` with real database operations using SQLAlchemy async sessions. This is a core dependency used by all agents.

**Details:**
- `mark_running(task_id)` — sets `agent_tasks.status = 'running'`
- `mark_completed(task_id, output_data)` — sets `status = 'completed'`, writes `output_data`
- `mark_failed(task_id, error)` — sets `status = 'failed'`, writes `error_message`
- `mark_waiting_for_approval(task_id)` — sets `status = 'waiting_for_approval'`
- `append_log(task_id, level, event_type, message, data)` — inserts `AgentLog` row
- All operations use injected `AsyncSession`
- `agent_context` passed to agents should include task primitives for logging

**Files to create/touch:**
- `app/core/task_manager.py` — replace stub with real implementation
- `app/db/session.py` — ensure async session factory is available

### 3.3 Build Web Research Tools

**Why:** The agent needs concrete tools to gather information. Two tools are required for Phase 2.

#### Tool A: `web_search`

Scoped web search via a configurable search API. For the hackathon demo, this will use a lightweight approach: either Tavily API (simple, structured results) or a SerpAPI wrapper. The tool interface abstracts the provider so the agent never knows which search backend is used.

**Interface:**
```python
# Tool name: "web_search"
# Input payload:
{
    "query": "AI-powered CRM funding round 2026",
    "max_results": 5
}
# Output ToolResult:
{
    "content": {
        "results": [
            {
                "title": "Company Raises $50M Series B",
                "url": "https://...",
                "snippet": "The company announced..."
            }
        ]
    },
    "sources": ["https://...", "https://..."]
}
```

**Implementation note:** For the initial build, implement a `SimulatedWebSearchTool` that returns realistic mock results so tests and demos work without network calls. This can be replaced with a real Tavily/SerpAPI adapter later without changing the agent.

#### Tool B: `extract_web_content`

Fetches a URL and extracts readable text content. Uses `httpx` + a simple HTML-to-text extraction (e.g., `markdownify` or manual `lxml` extraction).

**Interface:**
```python
# Tool name: "extract_web_content"
# Input payload:
{
    "url": "https://company.com/about"
}
# Output ToolResult:
{
    "content": {
        "url": "https://company.com/about",
        "title": "About Us - Company Inc",
        "text": "Company Inc was founded in 2015...",
        "extracted_at": "2026-07-16T12:00:00Z"
    },
    "sources": ["https://company.com/about"]
}
```

**Files to create/touch:**
- `app/tools/__init__.py` — new package
- `app/tools/web_search.py` — `WebSearchTool` (with simulated + real modes)
- `app/tools/web_extract.py` — `WebExtractTool`
- `app/tools/base.py` — optional shared tool utilities

### 3.4 Implement the Research Agent

**Why:** The core deliverable of Phase 2.

**Architecture:**

```
ResearchAgent
├── Constructor: receives AIProvider, ToolManager
├── run(context, task) -> AgentResult
│   ├── 1. Log: "research_started"
│   ├── 2. Extract company name/domain from task.input_data
│   ├── 3. Check DB for existing company profile or create stub
│   ├── 4. Ask LLM to generate research queries (structured output via prompt)
│   │      └── Prompt: "Given company X, generate 3-5 web search queries..."
│   ├── 5. For each query: call web_search tool → collect results
│   ├── 6. For top URLs: optionally call extract_web_content
│   ├── 7. Ask LLM to synthesize findings into structured profile
│   │      └── Prompt: "Synthesize these search results into a company profile..."
│   ├── 8. Build ResearchReport model
│   ├── 9. Persist: Company (update profile_data), ResearchReport
│   ├── 10. Log: "research_completed" with source count, provider info
│   └── 11. Return AgentResult with summary and output_data
```

**Research report structure (findings JSONB):**
```json
{
    "company_name": "Acme Corp",
    "domain": "acme.com",
    "industry": "SaaS / CRM",
    "employee_count": 250,
    "headquarters": "San Francisco, CA",
    "description": "Acme Corp provides AI-powered...",
    "funding": [
        {"round": "Series B", "amount": "$50M", "date": "2026-03"}
    ],
    "key_people": [
        {"name": "Jane Doe", "title": "CEO", "source": "..."}
    ],
    "signals": [
        "Hiring for enterprise sales roles → likely expanding upmarket",
        "New CFO hired → pre-IPO preparation signal"
    ],
    "pain_points": [
        "Scaling outbound sales team → likely needs BDR tools"
    ],
    "technologies": ["Salesforce", "HubSpot", "Snowflake"],
    "recent_news": [...]
}
```

**Agent dependencies — how they're wired:**
- `ResearchAgent` receives `AIProvider` and `ToolManager` at construction time
- This is set up in `build_default_registry()` in `app/agents/registry.py`
- The agent never imports `app.providers` or any concrete tool
- `TaskManager` is injected separately (into the API layer or a future orchestrator)

**Files to create/touch:**
- `app/agents/research.py` — full implementation
- `app/agents/registry.py` — update `build_default_registry()` to inject dependencies
- `app/core/contracts.py` — no changes needed (all contracts already defined)

### 3.5 API Endpoints

**Why:** The user needs to trigger research and view results. Following the architecture, HTTP handlers stay thin.

#### `POST /api/v1/research`

Trigger a research task for a company.

**Request body:**
```json
{
    "company_name": "Acme Corp",
    "domain": "acme.com",
    "lead_id": "uuid-optional"
}
```

**Response (202 Accepted):**
```json
{
    "task_id": "uuid",
    "status": "pending",
    "company_id": "uuid-or-null"
}
```

**Behavior:**
1. Look up or create `Company` record (if domain provided, check uniqueness)
2. Create `AgentTask` with `agent_type = "research"`, status `pending`
3. (Synchronously for Phase 2) Execute the agent via `AgentRuntime`
4. Return the task and report IDs

**Note:** A truly async dispatch (background worker) is deferred to a later phase. For now, the endpoint blocks until research completes, but returns 202 immediately and processes in a background `asyncio` task.

#### `GET /api/v1/research/{task_id}`

Poll task status.

**Response:**
```json
{
    "task_id": "uuid",
    "status": "completed",
    "agent_type": "research",
    "created_at": "...",
    "completed_at": "...",
    "error_message": null,
    "report_id": "uuid"
}
```

#### `GET /api/v1/reports/{report_id}`

Get the full research report.

**Response:**
```json
{
    "report_id": "uuid",
    "company_id": "uuid",
    "company_name": "Acme Corp",
    "domain": "acme.com",
    "summary": "Acme Corp is a SaaS company...",
    "findings": { ... },
    "sources": [ ... ],
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "created_at": "..."
}
```

#### `POST /api/v1/research/{task_id}/approve`

Approval boundary — mark task as approved so enrichment writes proceed (future).

**Files to create/touch:**
- `app/api/__init__.py` — new package
- `app/api/router.py` — main API router
- `app/api/research.py` — research endpoints
- `app/api/reports.py` — report read endpoints
- `app/main.py` — mount the API router

---

## 4. Data Flow Diagram

```
User → POST /api/v1/research
  │
  ├─ 1. Create/update Company in DB
  ├─ 2. Create AgentTask (status=pending)
  ├─ 3. TaskManager.mark_running(task_id)
  │
  ├─ AgentRuntime.execute(context, task)
  │   └─ ResearchAgent.run(context, task)
  │       │
  │       ├─ 4. Log: research_started (event_type="research.started")
  │       ├─ 5. AIProvider.generate() → research queries
  │       ├─ 6. ToolManager.execute("web_search", ...) → results
  │       ├─ 7. ToolManager.execute("extract_web_content", ...) → content
  │       ├─ 8. AIProvider.generate() → synthesize findings
  │       ├─ 9. Persist ResearchReport
  │       └─ 10. Return AgentResult
  │
  ├─ TaskManager.mark_completed(task_id, output_data)
  │
  └─ Response: { task_id, status: "completed", report_id }
```

---

## 5. Database Changes Required

**Observation:** The Phase 1 migration (`20260716_0001_initial_schema.py`) already includes all the tables needed for Phase 2. **No schema changes are required** for Phase 2.

The `research_reports` table already has:
- `company_id`, `lead_id`, `task_id` (foreign keys)
- `summary` (text)
- `findings` (JSONB — will hold the structured profile)
- `sources` (JSONB — array of source objects with URL, title, snippet)
- `provider`, `model` (strings for audit trail)

If we discover during implementation that we need additional columns (e.g., a status field on `research_reports`), we create a new Alembic migration.

---

## 6. Testing Strategy

### 6.1 Unit Tests

| Test | What it validates |
|------|-------------------|
| `test_web_search_tool` | Tool returns expected structure, tracks sources |
| `test_web_extract_tool` | Tool extracts text from mock HTML |
| `test_research_agent_empty_input` | Agent rejects missing company_name gracefully |
| `test_research_agent_happy_path` | Full agent run with mock AI + mock tools produces Report |
| `test_research_agent_source_tracking` | Sources from tools appear in report.sources |
| `test_task_manager_lifecycle` | DB transitions: pending → running → completed |
| `test_task_manager_logging` | Log entries are created and retrievable |
| `test_api_create_research_task` | POST /api/v1/research returns 202 with task_id |
| `test_api_get_report` | GET /api/v1/reports/{id} returns full report |

### 6.2 Test Infrastructure

**Mock AI provider:** A `FakeAIProvider` that returns canned responses based on prompt content. This lets tests run without network calls.

**Mock tools:** `SimulatedWebSearchTool` and `SimulatedWebExtractTool` return realistic but static results.

**Test database:** Use `pytest-asyncio` with a test PostgreSQL database or SQLite for unit tests. Given JSONB usage, PostgreSQL in a test container is preferred for CI.

### 6.3 Files to create
- `tests/test_research_agent.py`
- `tests/test_research_tools.py`
- `tests/test_task_manager.py`
- `tests/test_research_api.py`
- `tests/conftest.py` — fixtures for fake provider, mock tools, test DB session

---

## 7. How Future Agents Will Reuse This

### Tool Reuse

All tools live in `app/tools/` and are registered through `ToolManager`. Any agent can request any tool:

| Tool | Phase introduced | Used by |
|------|-----------------|---------|
| `web_search` | Phase 2 | Research, Qualification (validate claims) |
| `extract_web_content` | Phase 2 | Research, Qualification |
| `crm_lookup` | Phase 3 | Qualification |
| `email_draft` | Phase 4 | Outreach |
| `message_parse` | Phase 5 | Inbound |

### Task Manager Reuse

Every agent in every phase uses `TaskManager` for lifecycle tracking and audit logging. Phase 2's implementation is the permanent foundation.

### Provider Pattern Reuse

The `AIProvider` contract and `ProviderManager` resolution pattern remain unchanged. Future agents never import a provider SDK.

### Report Pattern Reuse

The `ResearchReport` model establishes the pattern for agent outputs:
1. Agent produces structured JSON
2. A typed DB model persists it
3. A read endpoint exposes it
4. The output serves as input to the next agent (e.g., QualificationAgent reads the ResearchReport)

### Agent Pattern Reuse

Phase 2 establishes the template for all agents:

```python
class SomeAgent(BaseAgent):
    agent_type = "some_agent"

    def __init__(self, ai: AIProvider, tools: ToolManager):
        self._ai = ai
        self._tools = tools

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        # 1. Extract input from task.input_data
        # 2. Use AIProvider.generate() to plan/reason
        # 3. Use ToolManager.execute() to gather data
        # 4. Use AIProvider.generate() to synthesize
        # 5. Persist result via injected DB session or TaskManager
        # 6. Return AgentResult with summary
```

---

## 8. Implementation Order

| Step | Task | Depends on |
|------|------|-----------|
| 1 | Implement AnthropicProvider.generate() | Nothing |
| 2 | Implement TaskManager with DB operations | Step 1 (optional dep) |
| 3 | Create `app/tools/` package with web_search + web_extract tools | Nothing |
| 4 | Create `tests/conftest.py` with fake provider + mock tools | Steps 1-3 |
| 5 | Implement ResearchAgent.run() | Steps 1-3 |
| 6 | Write unit tests for ResearchAgent + tools | Steps 4-5 |
| 7 | Create API endpoints (POST /research, GET /reports) | Steps 2, 5 |
| 8 | Write API integration tests | Step 7 |
| 9 | Update registry.py to wire dependencies | Step 5 |
| 10 | Update docs/index references | Everything |

---

## 9. Boundaries and Constraints

- **Do not** add LangGraph, CrewAI, or orchestration frameworks
- **Do not** add auth, user management, or multi-tenant separation
- **Do not** implement auto-sending or autonomous outbound actions
- **Do not** replace the existing agent contracts
- **Do not** import a concrete provider inside any agent
- **Do not** bypass `AgentTask` lifecycle for research operations
- **Do** keep HTTP handlers thin (logic in agents/tools, not endpoints)
- **Do** capture provider metadata and sources in every research report
- **Do** add a new Alembic migration if schema changes are needed
- **Do** respect the `requires_human_approval` flag for enrichment writes

---

## 10. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM provider call fails or times out | Wrap in try/except, mark task as failed, include error in log |
| Web search returns empty/no results | Agent produces partial report based on available data |
| HTML extraction is noisy | Use simple text extraction (strip tags, get meta description); refine later |
| No network in demo environment | SimulatedWebSearchTool provides realistic mock data for demos |
| API call blocks for too long | Initial sync execution is acceptable; background dispatch deferred |

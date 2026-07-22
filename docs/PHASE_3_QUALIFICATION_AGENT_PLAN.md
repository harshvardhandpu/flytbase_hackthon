# Phase 3 — Qualification Agent Implementation Plan

## Overview

Build a BDR qualification agent that scores a lead's fit against a configurable Ideal Customer Profile (ICP). The agent consumes the `ResearchReport` produced by Phase 2, applies deterministic rules and AI analysis, and produces an explainable score with priority classification.

---

## 1. Data Flow

```
ResearchReport (from Phase 2)
       │
       ▼
┌─────────────────────────────────────┐
│        QualificationAgent           │
│                                     │
│  1. Load ICP config                 │
│  2. Deterministic rules scoring     │
│     - Industry match                │
│     - Company size range            │
│     - Location/region               │
│  3. AI-powered signal scoring       │
│     - Buying signal analysis        │
│     - Company fit assessment        │
│  4. Composite score calculation     │
│  5. Priority assignment             │
│  6. Explainable reasoning           │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│       QualificationResult           │
│  - overall_score: 0-100             │
│  - icp_match_score: 0-100           │
│  - buying_signal_score: 0-100       │
│  - company_fit_score: 0-100         │
│  - priority: HOT/WARM/COLD          │
│  - reasons: [...]                   │
│  - risks: [...]                     │
│  - reasoning: text                  │
└─────────────────────────────────────┘
```

---

## 2. Input / Output Contract

### Input (consumed from ResearchReport findings and optional inline ICP override)

```json
{
  "report_id": "uuid",
  "company_name": "FlytBase",
  "domain": "flytbase.com",
  "industry": "Drone Services",
  "employee_count": 200,
  "location": "San Francisco",
  "description": "Drone fleet management platform...",
  "business_signals": ["Series A funding", "Hiring robotics engineers"],
  "pain_points": ["Scaling operations", "Manual fleet management"],
  "technology_signals": ["DJI integration", "API-first architecture"],
  "flytbase_relevance": "High - direct competitor alignment",
  "icp_config": {
    "industries": ["Drone Technology", "SaaS", "Automation"],
    "min_employees": 10,
    "max_employees": 500,
    "locations": ["US", "EU", "IN"]
  }
}
```

### Output (scoring result)

```json
{
  "overall_score": 91,
  "icp_match_score": 85,
  "buying_signal_score": 92,
  "company_fit_score": 88,
  "priority": "HOT",
  "reasons": [
    "+ Drone fleet operations detected",
    "+ Enterprise customer base",
    "+ Hiring robotics engineers",
    "+ Series A funding signals growth",
    "+ Technology stack compatible with FlytBase"
  ],
  "risks": [
    "- No direct purchase intent detected",
    "- May evaluate multiple vendors"
  ],
  "reasoning": "The company operates in the drone ecosystem...",
  "icp_config_id": "uuid",
  "report_id": "uuid",
  "task_id": "uuid"
}
```

---

## 3. DB Changes Required

Two new models, one migration (`alembic/versions/20260717_0001_phase3_qualification.py`).

### 3a. `IcpConfig` Model

```python
class IcpConfig(TimestampMixin, Base):
    __tablename__ = "icp_configs"

    id: Mapped[uuid.UUID] = PK, default=uuid.uuid4
    name: Mapped[str] = String(150), nullable=False
    description: Mapped[str | None] = Text
    industries: Mapped[list[str]] = JSONB, default=list         # e.g. ["Drone Technology", "SaaS"]
    min_employees: Mapped[int | None] = Integer
    max_employees: Mapped[int | None] = Integer
    locations: Mapped[list[str]] = JSONB, default=list          # e.g. ["US", "EU", "IN"]
    technology_signals: Mapped[list[str]] = JSONB, default=list  # e.g. ["drone", "DJI", "automation"]
    is_active: Mapped[bool] = Boolean, default=True
    version: Mapped[int] = Integer, default=1

    results: Mapped[list[QualificationResult]] = relationship(back_populates="icp_config")
```

**Why not inline/env config?** A DB-backed ICP config enables:
- Multiple ICP versions (e.g., different configs for different product lines)
- Audit trail of which config was used for each qualification
- Future UI for configuring ICP without deployments
- Default config seeded via migration or API

### 3b. `QualificationResult` Model

```python
class QualificationResult(TimestampMixin, Base):
    __tablename__ = "qualification_results"
    __table_args__ = (Index("ix_qualification_task_id", "task_id"),)

    id: Mapped[uuid.UUID] = PK, default=uuid.uuid4
    task_id: Mapped[uuid.UUID] = FK → agent_tasks.id, nullable=False
    lead_id: Mapped[uuid.UUID | None] = FK → leads.id
    company_id: Mapped[uuid.UUID] = FK → companies.id, nullable=False
    report_id: Mapped[uuid.UUID | None] = FK → research_reports.id
    icp_config_id: Mapped[uuid.UUID | None] = FK → icp_configs.id

    # Component scores
    overall_score: Mapped[int] = Integer, nullable=False            # 0-100
    icp_match_score: Mapped[int] = Integer, nullable=False          # 0-100
    buying_signal_score: Mapped[int] = Integer, nullable=False      # 0-100
    company_fit_score: Mapped[int] = Integer, nullable=False        # 0-100

    # Priority
    priority: Mapped[str] = String(10), nullable=False              # HOT | WARM | COLD

    # Explainability
    reasons: Mapped[list[str]] = JSONB, default=list               # Positive signals found
    risks: Mapped[list[str]] = JSONB, default=list                 # Negative signals / concerns
    reasoning: Mapped[str] = Text, default=""                      # Full LLM reasoning text

    # Metadata
    icp_inline_config: Mapped[dict[str, Any] | None] = JSONB       # Snapshot of ICP config used
    provider: Mapped[str | None] = String(100)
    model: Mapped[str | None] = String(255)

    # Relationships
    task: Mapped[AgentTask] = relationship()
    lead: Mapped[Lead | None] = relationship()
    company: Mapped[Company] = relationship()
    report: Mapped[ResearchReport | None] = relationship()
    icp_config: Mapped[IcpConfig | None] = relationship(back_populates="results")
```

### 3c. Migration Details

- New file: `alembic/versions/20260717_0001_phase3_qualification.py`
- Creates `icp_configs` and `qualification_results` tables
- Adds foreign keys to `agent_tasks`, `leads`, `companies`, `research_reports`
- Seeds a default ICP config for demo use

---

## 4. Scoring Architecture

### Hybrid Approach: Deterministic Rules + AI Judgment

```
┌────────────────────────────────────────────────┐
│               Scoring Pipeline                  │
│                                                │
│  Step 1: Deterministic ICP Match (0-100)       │
│    industry_match  = industry in industries?     │
│                         → 40 pts if yes, 0 if no│
│    size_score = clamp(employees, min, max)      │
│                         → 0-30 pts (scaled)     │
│    location_match = location in locations?      │
│                         → 30 pts if yes, 0 if no│
│                                                │
│  Step 2: AI Buying Signal Score (0-100)        │
│    LLM evaluates: business_signals              │
│                   pain_points                   │
│                   technology_signals            │
│    Factors: quantity, relevance, urgency        │
│                                                │
│  Step 3: AI Company Fit Score (0-100)          │
│    LLM evaluates: flytbase_relevance            │
│                   description                   │
│                   technology_signals            │
│    Factors: overlap with FlytBase solutions     │
│                                                │
│  Step 4: Composite Score & Priority            │
│    overall = LLM weighs all signals             │
│      OR deterministic: icp*0.40 + buy*0.35     │
│                         + fit*0.25              │
│    priority = HOT(>=70) | WARM(>=40) | COLD    │
└────────────────────────────────────────────────┘
```

### Score Thresholds

| Priority | Score Range | Meaning |
|----------|-------------|---------|
| **HOT**  | 70–100 | Ready for outreach; strong ICP fit + buying signals |
| **WARM** | 40–69 | Good fit but needs nurturing or more signals |
| **COLD** | 0–39 | Low priority; significant mismatch in ICP or signals |

---

## 5. QualificationAgent Design

### Class Structure

```python
class QualificationAgent(BaseAgent):
    agent_type = "qualification"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,      # For fetching report data from DB
        task_manager: TaskManager,
    ) -> None: ...

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        # 1. qualification_started
        # 2. Extract report_id, icp_config from input_data
        # 3. Load ResearchReport from DB (via tool or TM)
        # 4. Load IcpConfig (via tool or TM)
        # 5. icp_evaluation_started → deterministic scoring
        # 6. ai_scoring_started → LLM evaluates signals
        # 7. priority_assigned → composite score + threshold
        # 8. qualification_completed → persist QualificationResult
        # 9. Update Lead.score and Lead.score_reasoning
```

### Step Logging Events

| Event | Level | When |
|-------|-------|------|
| `qualification_started` | info | Task begins |
| `icp_config_loaded` | info | ICP config resolved |
| `deterministic_scoring_started` | debug | Rules executed |
| `deterministic_scoring_completed` | debug | Rule scores computed |
| `ai_scoring_started` | info | LLM evaluates signals |
| `ai_scoring_completed` | info | LLM returns scores |
| `priority_assigned` | info | Overall score + priority set |
| `qualification_completed` | info | Result persisted |
| `qualification_failed` | error | Any step fails |

### LLM Prompts

**Buying Signal Prompt** (system prompt):
```
You are a BDR qualification analyst. Evaluate the buying signals present
in a company's research profile for relevance to a drone fleet management platform.

Score the buying signals from 0-100 based on:
- Number and quality of business signals (funding, hiring, expansion)
- Relevance of pain points to drone automation solutions
- Technology stack compatibility with drone platforms
- Urgency indicators (recent initiatives, budget allocation)

Return ONLY a JSON object:
{
  "buying_signal_score": <0-100>,
  "company_fit_score": <0-100>,
  "reasons": [...],
  "risks": [...],
  "reasoning": "..."
}
```

**Composite Score Prompt** (system prompt):
```
You are a lead scoring analyst. Given the ICP match, buying signal analysis,
and company fit assessment, determine the overall lead score and priority.

Return ONLY a JSON object:
{
  "overall_score": <0-100>,
  "priority": "HOT" | "WARM" | "COLD",
  "reasons": [...positive signals...],
  "risks": [...concerns...]
}
```

---

## 6. Tool Design

Most scoring logic lives inside the agent itself (deterministic rules + LLM calls). One optional tool:

### `GetResearchReportTool` (optional)

```python
class GetResearchReportTool(BaseTool):
    name = "get_research_report"
    description = "Retrieve a company's research report by report_id or company_id"

    async def execute(self, payload) -> ToolResult:
        # Looks up ResearchReport from DB via session
        # Returns findings, sources, company profile
```

**Why make this a tool instead of direct DB access?** Following the agent pattern: agents use tools for data access, not direct DB queries. However, since the QualificationAgent will receive the report_id via task input_data and the research findings are already structured JSON, the agent can operate on the data directly without needing a tool. **Recommendation: skip the tool — pass report data directly via task input_data.**

### ICP Config Resolution

```python
class IcpConfigResolver:
    """Resolves ICP config from DB or inline override."""

    def __init__(self, session: Session) -> None: ...

    def resolve(self, config_id: UUID | None, inline: dict | None) -> IcpConfig:
        # Priority: inline override > config_id lookup > active default
```

---

## 7. API Endpoints

### POST `/api/v1/qualify`

Creates a qualification task and executes it synchronously.

**Request:**
```json
{
  "report_id": "uuid",
  "company_name": "Acme Corp",
  "domain": "acme.com",
  "icp_config_id": "uuid | null",
  "icp_config": {
    "industries": ["Drone Technology", "Automation"],
    "locations": ["US"]
  },
  "lead_id": "uuid | null"
}
```

At least one of `report_id` or `company_name` is required. If `report_id` is provided, the company profile is loaded from the existing research report. If only `company_name` is provided, the agent works with available company data (no research required — but less accurate).

**Response (202 Accepted):**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "score": 91,
  "priority": "HOT",
  "qualification_id": "uuid"
}
```

### GET `/api/v1/qualification/{task_id}`

Poll the qualification result.

**Response:**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "agent_type": "qualification",
  "score": 91,
  "priority": "HOT",
  "icp_match_score": 85,
  "buying_signal_score": 92,
  "company_fit_score": 88,
  "reasons": ["..."],
  "risks": ["..."],
  "reasoning": "...",
  "created_at": "2026-07-17T10:30:00Z",
  "completed_at": "2026-07-17T10:30:05Z"
}
```

### GET `/api/v1/icp-configs`

(Stretch goal) List available ICP configs.

### POST `/api/v1/icp-configs`

(Stretch goal) Create a new ICP config.

---

## 8. Implementation Order

| # | Component | Dependencies | Est. effort |
|---|-----------|-------------|-------------|
| 1 | DB models: `IcpConfig` + `QualificationResult` + migration | Phase 2 models | Small |
| 2 | `QualificationAgent` — deterministic scoring + AI scoring + step logging | #1, AIProvider, TaskManager | Medium |
| 3 | API endpoints: `POST /api/v1/qualify`, `GET /api/v1/qualification/{id}` | #2, router wiring | Medium |
| 4 | Update `registry.py` to accept QualificationAgent deps | #2 | Small |
| 5 | Update `router.py` `build_runtime()` to include all deps | #3, #4 | Small |
| 6 | Tests: QualificationAgent (unit + LLM scoring mocks) | #2 | Medium |
| 7 | Tests: API endpoints | #3 | Small |
| 8 | Tests: DB models + migration | #1 | Small |
| 9 | Update docs: `FREEBUFF_CONTEXT.md`, `ROADMAP.md` | all | Small |

---

## 9. Testing Strategy

### QualificationAgent Tests (8+ tests)

| Test | What it verifies |
|------|------------------|
| `test_deterministic_scoring_industry_match` | Correct ICP industry match weight |
| `test_deterministic_scoring_size_in_range` | Employee count within range → max points |
| `test_deterministic_scoring_size_out_of_range` | Employee count outside range → 0 points |
| `test_deterministic_scoring_location_match` | Location in allowed list → points |
| `test_full_workflow_returns_scores` | Complete run with FakeAIProvider returns 0-100 scores |
| `test_full_workflow_priority_assignment` | Correct priority based on score thresholds |
| `test_handles_missing_report_gracefully` | No research report → fallback scoring |
| `test_step_logging_events` | All expected log events are recorded |

### API Tests (4+ tests)

| Test | What it verifies |
|------|------------------|
| `test_qualify_with_report_id` | 202 response with task_id |
| `test_qualify_missing_fields` | 422 when both report_id and company_name missing |
| `test_get_qualification_invalid_uuid` | 422 for bad task_id |
| `test_get_qualification_not_found` | 404 for non-existent task |

### DB Tests (2-3 tests)

| Test | What it verifies |
|------|------------------|
| `test_create_icp_config` | Config persisted with correct defaults |
| `test_create_qualification_result` | Result persisted with all score fields |
| `test_resolve_active_config` | Default active config resolved correctly |

---

## 10. What Future Agents Reuse

| Pattern | Reused by |
|---------|-----------|
| `AIProvider + ToolManager + TaskManager` constructor injection | All future agents (Outreach, Inbound, Pipeline) |
| Step logging event pattern | All agents — same `append_log` API |
| `build_default_registry(deps)` wiring | Every agent added to the runtime |
| DB-backed task lifecycle | All agents — same `create_task → mark_completed` |
| Simulated → Real provider swap | QualificationScorer swaps to real LLM scoring |
| `BDR-focused structured output with reasoning` | Outreach agent (score-based messaging), Pipeline agent |

---

## 11. Architectural Contract Checks

- ✅ **Provider-neutral**: `QualificationAgent` imports `AIProvider` (Protocol), never `AnthropicProvider` or `OpenAIProvider`
- ✅ **No direct DB in agents**: All DB access through `TaskManager` or injected tools
- ✅ **Step logging**: Every phase logs via `TaskManager.append_log`
- ✅ **Simulated default**: Scoring runs deterministically first; AI scoring is LLM-powered via `AIProvider.generate()`
- ✅ **No new migration layer**: Uses the same Alembic migration approach as Phase 1
- ✅ **Thin endpoints**: API handlers parse HTTP, delegate to runtime, return results

---

## 12. Future-Proofing Notes

- **Real ICP config UI**: The `IcpConfig` model is ready for a settings UI. No schema changes needed.
- **Batch qualification**: The agent accepts a single report_id, but the architecture supports a batch endpoint by calling `run()` in a loop.
- **Scoring weights**: Currently hardcoded in prompts. Future: Store weights in `IcpConfig` as a `scoring_weights` JSONB field.
- **Time-decay**: Future: Subtract points if the research report is older than N days.
- **Feedback loop**: Future: Allow human reviewers to adjust scores and feed back into the LLM prompt.

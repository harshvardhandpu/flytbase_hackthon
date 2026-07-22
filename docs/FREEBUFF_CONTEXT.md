# Freebuff continuation context

## Project

ScoutOS is a provider-neutral, multi-agent BDR operating system. The goal is a polished July 25 hackathon demo where agents research, qualify, and draft outreach under human control.

## Completed in Phase 1

- Architecture docs under `docs/`
- FastAPI health application
- `Settings` configuration and provider resolution rules
- `AIProvider`, agent, memory, and tool contracts
- SQLAlchemy domain models and initial Alembic migration
- Agent skeletons registered by the runtime

## Completed in Phase 2 (Research Agent)

### What was built

**Provider Adapters** (`app/providers/`)
- `AnthropicProvider.generate()` — real HTTP calls to Anthropic Messages API via `httpx`.
- `OpenAIProvider.generate()` — real HTTP calls to OpenAI Chat Completions API via `httpx`.
- `FreeModelProvider` inherits from `AnthropicProvider` automatically.
- `ProviderError` exception for standardised error handling.
- `ProviderManager.resolve()` injects `Settings` into all provider constructors.
- **19 unit tests** covering success paths, system messages, HTTP errors, network errors, missing credentials.

**Tools Package** (`app/tools/`)
- `BaseTool` ABC with `name`, `description`, `execute(payload) -> ToolResult`.
- `ToolManager` — index-by-name registry + single `execute(name, payload)` entrypoint.
- `SimulatedWebSearchTool` — returns realistic mock results (FlytBase, drone inspection, or generic).
- `SimulatedContentExtractorTool` — returns realistic mock page content with title, text, timestamps.

**Task Manager** (`app/core/task_manager.py`)
- Full DB-backed lifecycle: `create_task` → `mark_running` → `mark_completed` / `mark_failed`.
- Structured audit logging: `append_log(task_id, level, event_type, message, data)` with structured `data` dict.
- Log retrieval: `get_logs(task_id)` ordered by creation time.

**Research Agent** (`app/agents/research.py`)
- Provider-neutral — receives `AIProvider` via constructor, never imports concrete providers.
- Full orchestration workflow with 7 step events.
- Robust error handling: LLM failures fall back to default queries.
- JSON parsing helpers for LLM output.

**API Endpoints** (`app/api/router.py`)
- `POST /api/v1/research`, `GET /api/v1/research/{task_id}`, `GET /api/v1/reports/{report_id}`

**Tests:** 60 tests (providers, tools, task manager, research agent, API)

## Completed in Phase 3 (Qualification Agent)

### What was built

**DB Models** (`app/db/models.py`)
- `IcpConfig` — Ideal Customer Profile configuration with industries, size ranges, locations, technology signals. Supports multiple configs with `is_active` flag.
- `QualificationResult` — Historical audit record separate from Lead. Stores all component scores, priority, reasoning, risks, and recommended BDR action.

**Migration** (`alembic/versions/20260717_0001_phase3_qualification.py`)
- Creates `icp_configs` and `qualification_results` tables.
- Seeds a default ICP config (drone technology, SaaS, automation; 10-500 employees; US/EU/IN).

**Qualification Agent** (`app/agents/qualification.py`)
- Provider-neutral — receives `AIProvider` via constructor.
- Hybrid scoring architecture:
  - **Deterministic**: Industry match (40pts) + company size (30pts, scaled) + location (30pts) → 0-100
  - **AI-powered**: LLM evaluates buying signals (business signals, pain points) and company fit (FlytBase relevance, technology signals) → 0-100 each
  - **Composite**: LLM weighs all signals for overall score and priority
- **Step logging** (9 events): `qualification_started` → `icp_config_loaded` → `deterministic_scoring_started/completed` → `ai_scoring_started/completed` → `composite_scoring_started` → `priority_assigned` → `qualification_completed`
- Priority thresholds: HOT (>=70), WARM (>=40), COLD (<40)
- BDR output includes urgency (Immediate/This week/This month) and suggested sales angle
- Error fallback: deterministic composite when LLM fails

**Qualification Output Structure:**
```json
{
  "overall_score": 91,
  "icp_match_score": 85,
  "buying_signal_score": 92,
  "company_fit_score": 88,
  "priority": "HOT",
  "reasoning": "2-3 sentence explanation",
  "reasons": ["+ Strong ICP match", "+ Buying signals detected"],
  "risks": ["- No direct purchase intent"],
  "recommended_bdr_action": {
    "urgency": "Immediate",
    "suggested_sales_angle": "Lead with drone automation..."
  },
  "icp_config_used": {
    "industries": ["Drone Technology", "SaaS"],
    "min_employees": 10,
    "max_employees": 500,
    "locations": ["US", "EU"]
  }
}
```

**API Endpoints** (`app/api/router.py`)
- `POST /api/v1/qualify` (202) — accepts `report_id` or `company_name`, optional `icp_config` inline override, optional `lead_id`. Persists `QualificationResult` and updates `Lead.score`.
- `GET /api/v1/qualification/{task_id}` — returns full scoring breakdown, reasons, risks, and recommended BDR action.

**Registry Wiring** (`app/agents/registry.py`)
- `QualificationAgent` receives `AIProvider`, `ToolManager`, `TaskManager` via constructor — same pattern as `ResearchAgent`.

**Tests (17 new, 77 total, all passing, lint clean):**
- 8 QualificationAgent tests (deterministic scoring, full workflow, step logging, LLM failure, priority thresholds, JSON parsing)
- 3 API endpoint tests (validation, error responses)
- Plus all 60 Phase 2 tests still pass

### How to run qualification

```bash
# Start the server
uvicorn app.main:app --reload

# 1. Run research first
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{"company_name": "FlytBase", "domain": "flytbase.com"}'

# 2. Qualify using the report_id from research
curl -X POST http://localhost:8000/api/v1/qualify \
  -H "Content-Type: application/json" \
  -d '{"report_id": "<report_id_from_research>"}'

# 3. Check qualification result
curl http://localhost:8000/api/v1/qualification/<task_id>
```

## Completed in Phase 4 (Outreach Agent)

### What was built

**DB Models** (`app/db/models.py`)
- `OutreachDraft` — stores generated drafts with full strategy, personalization, email content, and approval lifecycle (pending_approval → approved/rejected).
- `OutreachHistory` — immutable snapshot of approved drafts for permanent audit trail. Includes response tracking for future use.

**Migration** (`alembic/versions/20260718_0001_phase4_outreach.py`)
- Creates `outreach_drafts` and `outreach_history` tables.
- No existing tables modified — clean additive migration.

**Outreach Agent** (`app/agents/outreach.py`)
- Provider-neutral — receives `AIProvider` via constructor, never imports concrete providers.
- **3-stage LLM workflow** with independent step logging:
  1. **Strategy**: Recommends channel (email/linkedin/phone), urgency (Immediate/This week/This month), and strategic reasoning
  2. **Personalization Intelligence**: Generates company hook, detected pain point, and FlytBase value proposition tailored to the lead
  3. **Email Draft**: Composes subject line, email body, and follow-up suggestion
- Every step has its own log events: `strategy_generation_started/completed`, `personalization_started/completed`, `draft_generation_started/completed`
- Error events for each stage: `outreach_strategy_failed`, `outreach_personalization_failed`, `outreach_draft_failed`
- **No auto-send**: `AgentResult.requires_human_approval=True` and `TaskManager.mark_waiting_for_approval()`

**API Endpoints** (`app/api/router.py`)
- `POST /api/v1/outreach` (202) — generates draft from research and/or qualification context. Returns `status: "pending_approval"` and `draft_id`.
- `GET /api/v1/outreach/{task_id}` — returns full draft with strategy, personalization, email, and approval summary.
- `POST /api/v1/outreach/{draft_id}/approve` — marks draft as approved, creates `OutreachHistory` record. Does NOT send.
- `POST /api/v1/outreach/{draft_id}/reject` — marks draft as rejected with reason.
- `GET /api/v1/outreach/{draft_id}/history` — returns approval/send history for a draft.

**Registry Wiring** (`app/agents/registry.py`)
- `OutreachAgent` promoted from skeleton to full implementation — receives `AIProvider`, `ToolManager`, `TaskManager` via constructor, matching Phase 2/3 patterns.

**Tests (15 new, 89 total, all passing, lint clean):**
- 15 OutreachAgent tests: full workflow, step logging, human approval flag, missing context handling, LLM failure fallbacks (strategy + draft), structured output validation, JSON parsing
- 12 API tests cover validation (422) and not-found (404) for all 5 endpoints
- All 74 existing Phase 2/3 tests continue to pass without modification

### How to run outreach

```bash
# Start the server
uvicorn app.main:app --reload

# 1. Research a company
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{"company_name": "SkyGrid Inc.", "domain": "skygrid.io"}'

# 2. Qualify (optional but recommended)
curl -X POST http://localhost:8000/api/v1/qualify \
  -H "Content-Type: application/json" \
  -d '{"report_id": "<report_id>"}'

# 3. Generate outreach draft from research + qualification
curl -X POST http://localhost:8000/api/v1/outreach \
  -H "Content-Type: application/json" \
  -d '{
    "report_id": "<report_id>",
    "qualification_id": "<qualification_id>"
  }'
# Returns task_id and draft_id with status="pending_approval"

# 4. View the full draft
curl http://localhost:8000/api/v1/outreach/<task_id>

# 5. Approve or reject
curl -X POST http://localhost:8000/api/v1/outreach/<draft_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "harsh@flytbase.com"}'
```

### Architecture preserved
- ✅ Provider-neutral — `OutreachAgent` only imports `AIProvider` Protocol
- ✅ `AIProvider + ToolManager + TaskManager` constructor injection — same as Phases 2 and 3
- ✅ Step logging via `TaskManager.append_log()` — all 9+ events logged
- ✅ No DB access from agent — data passed through `input_data`
- ✅ `requires_human_approval=True` — no auto-send
- ✅ `OutreachHistory` — immutable audit records
- ✅ New migration, no existing models modified

## Completed in Phase 5 (Inbound & Pipeline Agent)

### What was built

**DB Models** (`app/db/models.py`)
- `InboundMessage` — stores raw message content + AI analysis (intent, sentiment, urgency, extracted details) + suggested reply + approval lifecycle (pending_review → approved/rejected). Links to `leads`, `contacts`, `companies`, and `conversations`.
- `PipelineStage` — configurable pipeline stage definitions with name, display name, order, color, and active flag.
- `PipelineStatus` — per-lead pipeline history tracking. The `is_current` record holds the lead's present stage, historical records provide the full pipeline journey. Stores reason, signal summary, and recommended next action.

**Migration** (`alembic/versions/20260720_0001_phase5_inbound_pipeline.py`)
- Creates `inbound_messages`, `pipeline_stages`, `pipeline_status` tables.
- Seeds 8 default pipeline stages: new → researching → qualified → outreach → meeting_scheduled → negotiation → closed_won → closed_lost.
- No existing tables modified — clean additive migration.

**Inbound Agent** (`app/agents/inbound.py`)
- Provider-neutral — receives `AIProvider` via constructor, never imports concrete providers.
- **2-stage LLM workflow** with independent step logging:
  1. **Intent analysis**: Classifies intent (question/objection/purchase_intent/meeting_request/etc.), sentiment (positive/neutral/negative), urgency (high/medium/low), and extracts structured details (topics, pain points, interest signals, contact role, company size hint, timeline hint).
  2. **Lead action + reply**: Determines lead action (create_lead/update_lead/no_action), suggested status change, generates a suggested reply, and follow-up suggestion.
- **Conditional human approval**: `requires_human_approval=True` when a reply is generated; `False` for purely informational messages (unsubscribe, spam).
- **Deterministic shortcuts**: Unsubscribe requests and empty messages are handled without LLM calls.
- **8 step-logging events**: `inbound_started`, `intent_analysis_started/completed`, `reply_generation_started/completed`, `inbound_completed`, plus error events.

**Pipeline Agent** (`app/agents/pipeline.py`)
- Provider-neutral — receives `AIProvider` via constructor.
- **Hybrid deterministic + LLM architecture**:
  - **Deterministic rules**: Stage health computation (healthy/stale/critical based on days-in-stage thresholds) and stagnation risk (low/moderate/high based on time + engagement count). Thresholds: new=7d, researching=5d, qualified=3d, outreach=7d, meeting_scheduled=14d, negotiation=30d.
  - **LLM evaluation**: Evaluates pipeline position, overall lead health (good/fair/poor), engagement level, signal decay, and recommends next best action (advance/follow_up/nurture/re_qualify/close/no_action) with priority (urgent/soon/monitor).
- **Never requires human approval**: `requires_human_approval=False` — recommendations only, no auto-transition.
- **6 step-logging events**: `pipeline_evaluation_started`, `lead_data_aggregated`, `deterministic_analysis_started/completed`, `llm_evaluation_started/completed`, `pipeline_evaluation_completed`.
- **Engagement counting**: Aggregates signals from research tasks, qualification results, outreach drafts, inbound messages, and conversations.

**API Endpoints** (`app/api/router.py`)
- Inbound:
  - `POST /api/v1/inbound` (202) — process inbound message, returns analysis with `message_id` and `status: "pending_review"` if approval needed.
  - `GET /api/v1/inbound/{task_id}` — returns full analysis with message, intent/sentiment/urgency, extracted details, suggested reply, and approval summary.
  - `POST /api/v1/inbound/{message_id}/approve` — approves suggested reply, applies `suggested_status` to lead.
  - `POST /api/v1/inbound/{message_id}/reject` — rejects with reason.
- Pipeline:
  - `POST /api/v1/pipeline/evaluate` (202) — evaluates lead pipeline position. Aggregates data from all phases (research, qualification, outreach, inbound, conversations) before calling the agent.
  - `GET /api/v1/pipeline/leads` — lists leads with current pipeline status, stage health, days in stage, score, and priority. Supports filtering by stage and health.
  - `GET /api/v1/pipeline/{task_id}` — returns full evaluation with lead health and recommended action.
  - `POST /api/v1/pipeline/{lead_id}/advance` — human override to advance a lead stage. Creates new `PipelineStatus` record, marks previous as non-current, updates `Lead.status`.

**Registry Wiring** (`app/agents/registry.py`)
- Both `InboundAgent` and `PipelineAgent` promoted from skeletons to full implementations — receive `AIProvider`, `ToolManager`, `TaskManager` via constructor.

**Tests (26 new, 102 total, all passing, lint clean):**
- 10 InboundAgent tests: full workflow, intent classification, sentiment, existing lead, human approval, step logging, empty message, LLM fallback, extracted details
- 6 PipelineAgent agent tests + 10 deterministic rule tests: full workflow, healthy/stale/critical detection, stagnation risk, LLM fallback, no history, step logging, segment health and risk thresholds
- 10 API tests: validation (422), not-found (404), response schema validation
- 13 provider manager tests continue to pass

### Architecture preserved
- ✅ Provider-neutral — both agents import only `AIProvider` Protocol, never concrete providers
- ✅ `AIProvider + ToolManager + TaskManager` constructor injection — matches Phases 2-4
- ✅ Conditional `requires_human_approval` — InboundAgent uses it (reply-generated), PipelineAgent never
- ✅ Step logging via `TaskManager.append_log()` — all events logged with structured data
- ✅ No DB access from agents — all data passed through `input_data`
- ✅ `PipelineStatus` — historical records for audit trail
- ✅ New migration, no existing models modified
- ✅ `_compute_stage_health` shared between router and agent

### How to run inbound and pipeline

```bash
# Start the server
uvicorn app.main:app --reload

# Process an inbound message
curl -X POST http://localhost:8000/api/v1/inbound \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "john@skygrid.io",
    "from_name": "John Smith",
    "subject": "Demo request",
    "body": "Hi, we operate 50+ drones and would like to see how FlytBase can help us automate our inspection workflows. Can we schedule a demo?",
    "channel": "email",
    "lead_id": null
  }'

# View inbound analysis
curl http://localhost:8000/api/v1/inbound/<task_id>

# Approve or reject
curl -X POST http://localhost:8000/api/v1/inbound/<message_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "bdr@flytbase.com"}'

# Evaluate pipeline for a lead (requires an existing lead_id)
curl -X POST http://localhost:8000/api/v1/pipeline/evaluate \
  -H "Content-Type: application/json" \
  -d '{"lead_id": "<lead_id>"}'

# List leads with pipeline status
curl http://localhost:8000/api/v1/pipeline/leads

# Advance a lead manually
curl -X POST http://localhost:8000/api/v1/pipeline/<lead_id>/advance \
  -H "Content-Type: application/json" \
  -d '{"new_stage": "meeting_scheduled", "reason": "Demo confirmed", "advanced_by": "bdr@flytbase.com"}'
```

## Completed in Phase 6 — Demo Polish (Mission Control Dashboard)

### What was built

**Frontend Stack** (`app/templates/`, `app/static/`)
- Zero build pipeline — Jinja2 templates served directly by FastAPI
- Tailwind CSS + Alpine.js + Alpine.js Collapse plugin via CDN
- Dark "Mission Control" theme (slate-900/800/700 palette, Inter font)
- 7 Jinja2 template files covering all views

**Views created (Day 1-4):**

| View | File | Features |
|------|------|----------|
| Dashboard | `dashboard.html` | Stats bar (total/HOT/pending/stale), pipeline snapshot (8 stages with health dots), quick actions, recent activity feed |
| Leads List | `leads.html` | Table with search, stage/health filters, column sorting (company, stage, score, health, days), priority badges, click-to-detail |
| Lead Detail | `lead_detail.html` | 4-card layout: Company Profile, Qualification (SVG score gauge + component bars + reasons/risks), Outreach Draft (approve/reject), Pipeline Position (health + recommended action) |
| Outreach | `outreach.html` | Draft queue with status badges, inline approve/reject, full detail modal with email preview |
| Pipeline Kanban | `pipeline.html` | 8 horizontal-scrollable stage columns, lead cards (score/health/days/priority), advance-to-next-stage button per card, stats bar |
| Inbound Messages | `inbound.html` | Message queue sorted by status, expandable cards (original message, analysis grid, suggested reply), inline approve/reject |
| Activity Log | `activity.html` | Agent type filter bar, status filter, expandable task cards with step-level timeline logs (via `/api/v1/activity/tasks/{task_id}/logs`), show/hide raw JSON data |

**Backend Changes**
- `app/main.py` — Mounted Jinja2Templates + StaticFiles, added 7 frontend routes (/, /leads, /leads/{id}, /outreach, /pipeline, /inbound, /activity)
- `app/api/router.py` — Added `GET /api/v1/activity` (activity feed with filtering) + `GET /api/v1/activity/tasks/{task_id}/logs` (step-level log retrieval)
- `pyproject.toml` — Added `jinja2>=3.1,<4` dependency, E501 ignore for `scripts/*.py`

**Seed Script** (`scripts/seed_demo_data.py`)
- Creates 5 demo companies with complete lifecycle data:
  - SkyGrid Inc. (Drone Technology, SF, 320 employees, Series B, meeting_scheduled stage)
  - AeroVista (Aerial Imaging, Austin, 85 employees, outreach stage)
  - DroneFleet Logistics (Logistics, Chicago, 210 employees, outreach stage)
  - AirMap Technologies (Airspace Management, Berlin, 55 employees, qualified stage)
  - PrecisionAg Drones (Agri-tech, Bangalore, 42 employees, researching stage)
- Full agent lifecycle per company: research reports → qualification scores → outreach drafts → pipeline status
- 3 inbound messages from SkyGrid (meeting_request approved, trial_request pending, technical inquiry pending)
- Agent logs for all tasks with structured step-level details
- Default ICP config + 8 pipeline stages
- Fully idempotent — safe to run multiple times

**Usage:**
```bash
# Seed the database with demo data
python scripts/seed_demo_data.py

# Start the server and open Mission Control
uvicorn app.main:app --reload
# Then visit http://localhost:8000
```

### Architecture preserved
- ✅ No agent/provider/migration changes — frontend is purely additive
- ✅ All data served through existing API endpoints
- ✅ Dark theme consistent with hackathon demo aesthetic
- ✅ Loading states, empty states, error handling on all views
- ✅ 5 CDN dependencies with offline fallback (Tailwind, Alpine.js, Collapse plugin, Inter font, Heroicons)

### Tests & Lint
- **102/102 tests passing** (all existing backend tests preserved)
- **Lint clean** (ruff passes with no errors)

**Plan:** See [PHASE_6_DEMO_POLISH_PLAN.md](PHASE_6_DEMO_POLISH_PLAN.md)

---

## Completed in Phase 6.5 — Inline Editor & Diff Comparison

### What was built

**Inline Editor for Outreach Drafts** (`app/templates/outreach.html`)
- BDR can edit email subject (input) and body (textarea) before approving
- 3-state toggle: **Edit** → **Preview** → **Edited** (yellow badge when edits exist)
- **Revert to Original** button — resets both fields to AI-generated originals in one click
- Character counts: Subject `{n}/200` with yellow warning at 180+, Body `{n}/5000` with yellow at 4500+, both with `maxlength`
- **"Modified" label** ("✏️ Modified") appears next to char count when `draftDirty` is true
- Stale-edit guard: modal approve always sends edits; card-level approve never sends (prevents leaking edits from a previous modal session)
- Bug fix: `draft.originalSubject` → `this.originalSubject` — comparison was always detecting false edits
- Cleanup: removed redundant `hasUnsavedEdits` snapshot — `draftDirty` getter works live in both modes
- No backend changes needed — API already accepted `edited_subject`/`edited_body`

**Diff View for Email Drafts** (`app/templates/outreach.html`)
- Client-side word-level LCS (Longest Common Subsequence) diff algorithm
- Green background + text for added words, red background + strikethrough for removed words
- Legend bar explaining color coding
- Diff results cached on enter — avoids recomputing DP table on every Alpine.js re-render
- Diff button appears only when `draftDirty` is true (i.e., edits exist)
- 10 state transitions verified: edit→diff (syncs + caches), diff→edit, diff→preview, preview→diff, approve from diff mode, etc.

**Extended Diff for Intelligence Sections** (`app/templates/outreach.html`, `app/api/router.py`)
- Same tri-mode (Preview / Edit / Diff) applied to all 5 intelligence fields:
  - Company Situation Summary
  - Detected Business Problems (textarea with "one per line" helper)
  - Operational Risks (textarea with "one per line" helper)
  - FlytBase Fit Summary
  - Recommended Sales Angle
- **`intelDirty`** getter — detects changes across all 5 intelligence fields independently
- **`overallDirty`** getter — combines `draftDirty || intelDirty` for Diff button + "Edited" badge
- **`_syncIntelEditsToDraft()`** — syncs intelligence edits to draft; arrays round-trip through `join('\n')` → textarea → `split('\n').filter(Boolean)`
- **`revertIntelToOriginal()`** — separate revert button for intelligence edits (alongside existing email revert)
- **`cachedIntelDiff`** — pre-computed LCS diffs for 5 fields, cached on diff enter
- Backend: `ApproveRequest.edited_intelligence` merges edited fields into `CompanyIntelligenceBrief.brief_data` while preserving unedited fields

**Tests (5 new, 156 total)**
- `TestOutreachApproveIntelligenceMerge` class in `tests/test_outreach_api.py`:
  1. No `edited_intelligence` — brief unchanged
  2. All 5 fields edited — all updated, unedited preserved
  3. Partial merge (2 of 5) — only those 2 updated
  4. Empty dict — no changes
  5. Edited intelligence without existing brief — no crash
- All 156 tests passing, lint clean (ruff pass)

### Browser verification (all passed, zero console errors)
- Opened pending draft → edited all 5 intelligence fields → toggled diff view → verified green/red highlights → approved → verified persistence on hard refresh
- Inline editor: edit → preview → edited badge → revert to original → approve — all verified
- Diff view: 10-step flow with LCS word-level highlighting confirmed working

### Architecture preserved
- ✅ AIProvider interface untouched
- ✅ ToolManager + TaskManager pattern unchanged
- ✅ BaseAgent pattern preserved
- ✅ No new DB migrations — intelligence data stays in `CompanyIntelligenceBrief.brief_data`
- ✅ No new models — all changes are frontend + API merge logic

## Codex Changes (July 23, 2026)

### What Was Done

**Inline Editor for Outreach Drafts:**
- Client-side Alpine.js editor with 3-state toggle (Edit/Preview/Edited)
- Character counts with `maxlength` and yellow warnings
- "Revert to Original" and "Modified" label
- Stale-edit guard for card-level vs modal approve
- Cleanup of redundant `hasUnsavedEdits` state

**Diff View for Email Drafts:**
- Word-level LCS diff algorithm with green/red highlights
- Cached diff computation (avoids DP recalculation on Alpine.js re-renders)
- 10 state transitions verified

**Extended Diff for Intelligence Sections:**
- 5 editable intelligence fields with tri-mode (Preview/Edit/Diff)
- Array fields round-trip through newline-separated textareas
- Backend merge logic: `ApproveRequest.edited_intelligence` merged into `CompanyIntelligenceBrief.brief_data`
- `overallDirty` and `intelDirty` getters for combined dirty detection

**Documentation Updated:**
- `docs/FREEBUFF_CONTEXT.md` — Added Phase 6.5 and updated Codex Changes
- `docs/ROADMAP.md` — Updated with Phase 6.5 and Codex Changes sections
- `docs/CODEX_HANDOFF.md` — Updated with latest changes

### Files Modified
- `app/api/router.py` — Extended `ApproveRequest` with `edited_intelligence`, merge logic in `approve_outreach_draft()`
- `app/templates/outreach.html` — Added inline editor, diff view, extended intelligence diff, Alpine.js state management
- `tests/test_outreach_api.py` — Added 5 tests for `edited_intelligence` merge logic (plus ruff format cleanup)

### Known State
- **Tests:** 156/156 passing (was 151)
- **Lint:** Clean (ruff passes)
- **Server:** Running on http://localhost:8000
- **PostgreSQL:** Running on localhost:5432
- **Latest Migration:** `20260721_0001` (Company Intelligence Briefs)
- **Approved browser verification:** All intelligence diff flow steps passed with zero console errors

### How to continue

```bash
cd /home/harshdev/flytbase_hackthon
source .venv/bin/activate
uvicorn app.main:app --reload
```

See `docs/CODEX_HANDOFF.md` for comprehensive continuation instructions.

## Do not change

- Do not let agents import `app.providers.*` directly.
- Do not bypass task logging or approval boundaries for external actions.
- Do not replace PostgreSQL operational records with a vector store.
- Do not build UI, CRM integrations, automatic sending, or a heavyweight orchestration framework in the research phase.
- Preserve the initial migration; add a new migration for changes.

## Working conventions

Read `ARCHITECTURE.md`, `AGENT_DESIGN.md`, and `DEVELOPMENT_GUIDE.md` before coding. Keep endpoints thin, tests focused, models typed, and docs updated. Provider credentials belong only in environment variables. Every agent follows the same pattern: `AIProvider + ToolManager + TaskManager` via constructor injection.

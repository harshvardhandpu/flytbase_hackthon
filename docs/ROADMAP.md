# Roadmap to July 25, 2026

## Phase 1 — foundation ✅

Documentation, contracts, configuration, data models, migration, and health API. No agent carries out real work.

## Phase 2 — research ✅

Implement a research agent with approved source tools, structured company reports, citations, task execution, and a human-readable report endpoint.

**Delivered:** 60 tests, provider adapters, tools, TaskManager, ResearchAgent, API endpoints.

**Plan:** See [PHASE_2_RESEARCH_AGENT_PLAN.md](PHASE_2_RESEARCH_AGENT_PLAN.md).

## Phase 3 — qualification ✅

Implement a qualification agent that scores leads against a configurable ICP using hybrid deterministic + AI scoring. Persists historical QualificationResult records separate from Lead.

**Delivered:**
- `IcpConfig` and `QualificationResult` DB models + migration (with seed data)
- `QualificationAgent` with hybrid scoring (deterministic rules + LLM signal evaluation)
- 9 step-logging events covering the full qualification lifecycle
- BDR output with priority (HOT/WARM/COLD), urgency, and suggested sales angle
- API endpoints: `POST /api/v1/qualify`, `GET /api/v1/qualification/{task_id}`
- **77 tests** — all passing, lint clean

**Plan:** See [PHASE_3_QUALIFICATION_AGENT_PLAN.md](PHASE_3_QUALIFICATION_AGENT_PLAN.md).

## Phase 4 — outreach ✅

Implement an outreach intelligence agent that consumes ResearchReport + QualificationResult to generate editable email drafts with a human approval boundary. No auto-send.

**Delivered:**
- `OutreachDraft` and `OutreachHistory` DB models + migration
- `OutreachAgent` with 3-stage LLM workflow (strategy → personalization → draft), 9 step-logging events, `requires_human_approval=True`
- API endpoints: `POST /api/v1/outreach`, `GET /api/v1/outreach/{task_id}`, approve/reject/history
- Registry wiring — promoted from skeleton to full implementation
- **89 tests** — all passing, lint clean
- Provider-neutral architecture preserved throughout

**Plan:** See [PHASE_4_OUTREACH_AGENT_PLAN.md](PHASE_4_OUTREACH_AGENT_PLAN.md)

## Phase 5 — inbound and pipeline ✅

Implement inbound message processing (intent classification, reply generation, human approval) and pipeline intelligence (stage health, stagnation detection, next-action recommendations).

**Delivered:**
- `InboundMessage`, `PipelineStage`, `PipelineStatus` DB models + migration (with 8 seeded pipeline stages)
- `InboundAgent` with 2-stage LLM workflow (intent analysis → reply generation), conditional human approval, 8 step-logging events
- `PipelineAgent` with hybrid deterministic rules + LLM evaluation, stage health + stagnation risk detection, 6 step-logging events
- API endpoints: `POST/GET /api/v1/inbound`, approve/reject, `POST /api/v1/pipeline/evaluate`, `GET /api/v1/pipeline/leads`, `GET /api/v1/pipeline/{task_id}`, `POST /api/v1/pipeline/{lead_id}/advance`
- **102 tests** — all passing, lint clean
- Provider-neutral architecture preserved throughout

**Plan:** See [PHASE_5_INBOUND_PIPELINE_AGENT_PLAN.md](PHASE_5_INBOUND_PIPELINE_AGENT_PLAN.md)

## Phase 6 — demo polish ✅

**Delivered:** Mission Control dashboard — single-page, dark-theme, Jinja2 + Alpine.js frontend with 7 views covering all 5 agent phases. Comprehensive seed script (`scripts/seed_demo_data.py`) with 5 demo companies, full lifecycle data, and 102 passing tests.

### Views
- **Dashboard** — stats bar, pipeline snapshot, activity feed
- **Leads List** — searchable/sortable/filterable table, click-to-detail
- **Lead Detail** — 4-card layout (Company Profile, Qualification, Outreach, Pipeline)
- **Outreach Drafts** — queue with approve/reject modal
- **Pipeline Kanban** — 8 horizontal-scrollable stage columns with advance actions
- **Inbound Messages** — expandable analysis cards with approve/reject
- **Activity Log** — agent type filter, status filter, step-level timeline logs

**Plan:** See [PHASE_6_DEMO_POLISH_PLAN.md](PHASE_6_DEMO_POLISH_PLAN.md)

## Phase 6.5 — Inline Editor & Diff Comparison ✅

**Completed:** July 23, 2026

**Delivered:** Inline editor for outreach drafts (edit email subject/body before approval), word-level LCS diff view, extended diff for intelligence sections — all within the existing modal approval UI. **156 tests passing, lint clean.**

### What was built

**Inline Editor** (`app/templates/outreach.html`)
- 3-state toggle: Edit → Preview → Edited (yellow badge)
- Character counts with maxlength and yellow threshold warnings
- "Revert to Original" button + "✏️ Modified" label
- Stale-edit guard: modal vs card-level approve

**Diff View** (`app/templates/outreach.html`)
- Client-side word-level LCS algorithm
- Green highlights for added words, red strikethrough for removed
- Cached diff computation (avoids DP recalculation on re-renders)
- Legend bar for color coding

**Extended Intelligence Diff** (`app/templates/outreach.html`, `app/api/router.py`)
- 5 editable intelligence fields: Company Situation Summary, Detected Business Problems, Operational Risks, FlytBase Fit Summary, Recommended Sales Angle
- Each with tri-mode: Preview / Edit (textarea) / Diff (LCS word-level)
- Arrays round-trip through `join('\n')` → textarea → `split('\n').filter(Boolean)`
- Backend: `ApproveRequest.edited_intelligence` merged into `CompanyIntelligenceBrief.brief_data` preserving unedited fields

**Tests (5 new, 156 total)**
- `test_approve_without_edited_intelligence` — null/absent, brief unchanged
- `test_approve_with_all_intelligence_fields` — all 5 fields updated, unedited preserved
- `test_approve_with_partial_intelligence_merge` — 2 of 5 fields updated
- `test_approve_with_empty_edited_intelligence` — `{}`, no changes
- `test_approve_with_edited_intelligence_no_brief` — no crash when brief absent
- All 156 passing, lint clean

### Browser verification
- Full 11-step flow: open draft → edit 5 intelligence fields → toggle diff → verify green/red highlights → approve → hard refresh → persistence confirmed
- Zero console errors (only expected Tailwind CDN production warning)

## Phase 7 — Account Intelligence Engine ✅

**Completed:** July 23, 2026

**Delivered:** Real web search via Tavily API, web content extraction, LLM-powered company intelligence analysis, upgraded ResearchAgent with enriched output. **178 tests passing, lint clean.**

### What was built

**Real Web Search Tool** (`app/tools/web_search.py`)
- Tavily Search API integration with automatic simulated fallback
- Uses `httpx` for async HTTP calls
- Falls back to deterministic mock results when API key is absent

**Web Content Extractor Tool** (`app/tools/web_extractor.py`)
- Fetches URLs and extracts clean readable text via HTTP GET + regex HTML stripping
- Falls back to simulated page content on network errors

**Account Intelligence Layer** (`app/intelligence/account_research.py`)
- `AccountResearchIntelligence` — transforms raw research into structured BDR intelligence
- Provider-neutral — uses `AIProvider` interface
- Fields: company_situation, business_problems, operational_risks, growth_signals, buying_signals, industry_incidents, citations
- Deterministic fallback when LLM analysis fails

**Upgraded ResearchAgent** (`app/agents/research.py`)
- Integrates Account Intelligence Engine
- New step events: search_started/completed, extraction_started, intelligence_analysis_started/completed
- Output includes citations and intelligence_metadata

**Database Migration** (`20260723_0001`)
- Added `citations` (JSONB) and `intelligence_metadata` (JSONB) to `research_reports`
- Additive — no existing tables modified

**Improved Outreach Intelligence Brief** (`app/intelligence/outreach_brief.py`)
- `build()` now accepts optional `account_intelligence` parameter
- Preferentially uses Account Intelligence fields when available

**Tests (22 new, 178 total)**
- 7 tests: WebSearchTool
- 7 tests: WebContentExtractorTool
- 8 tests: AccountResearchIntelligence
- All 156 existing tests continue to pass

### Configuration
```env
# Search Provider (tavily or simulated)
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-your-key-here
```

### More details
See [docs/ACCOUNT_INTELLIGENCE.md](docs/ACCOUNT_INTELLIGENCE.md)

---

## Phase 8 — Demo Scenario ✅

**Completed:** July 24, 2026

**Delivered:** One-click judge demo with dedicated `/demo` endpoint, "Launch Demo Mission" button that seeds data and redirects to dashboard, demo indicator badges on lead detail/outreach/pipeline views, comprehensive `docs/DEMO_SCENARIO.md` with 3-minute judge walkthrough, and a one-command demo launcher CLI.

**All 185 tests passing, lint clean.**

### What was built

**Demo Mode** (`app/main.py` + `app/templates/demo.html`)
- `GET /demo` — Judge-facing demo introduction page
- `POST /demo/seed` — One-click data seeding + redirect
- Sidebar "🎯 Demo Scenario" navigation link

**Demo Indicators** (3 templates)
- Lead detail, outreach cards, pipeline cards show "🎯 Demo Account"/"🎯 Demo" badge for SkyGrid

**Demo CLI Launcher** (`scripts/demo.py` + `tests/test_demo_script.py`)
- `python scripts/demo.py` — one-command environment setup + data seeding + verification
- Checks: Python version, virtual environment, `.env` file, PostgreSQL connection
- Runs: Alembic migrations + demo seed script (idempotent)
- Verifies server health (`GET /health`)
- Prints formatted demo instructions with judge walkthrough and talking points
- 18 tests covering file structure, functions, output sections, exit codes

**Documentation**
- `docs/DEMO_SCENARIO.md` — Updated with `python scripts/demo.py` instructions
- Updated `FREEBUFF_CONTEXT.md`, `ROADMAP.md`, `CODEX_HANDOFF.md`

### Demo flow
```
$ python scripts/demo.py
        ↓
Environment Check → Database Prep → Server Check → Instructions
        ↓                           ↓
   Pass or fail                  /demo flow
```


---

## Codex Handoff — Final Verification ✅

**Completed:** July 21, 2026 (initial) / July 23, 2026 (updated) / July 24, 2026 (Demo Scenario)

**Delivered:** Project verification, DB fix, inline editor, diff view, extended intelligence diff, Account Intelligence Engine, lint cleanup, documentation.

### What was built (July 23 updates)
- Inline editor for outreach email drafts with editable subject/body, revert, character counts
- Word-level LCS diff view for email drafts
- Extended diff for all 5 intelligence sections
- Backend merge logic for `edited_intelligence`
- **Account Intelligence Engine**: WebSearchTool, WebContentExtractorTool, AccountResearchIntelligence, upgraded ResearchAgent
- Database migration for citations and intelligence_metadata
- 22 new tests

### What was verified
- PostgreSQL running and migrated to latest (`20260723_0001`)
- All **178 tests passing** (was 156)
- Lint clean (ruff pass)
- 22 new tests for web search, extraction, and account intelligence

### Post-Hackathon Ideas
- Additional search providers (Google Custom Search, Bing)
- Deeper HTML extraction with readability/trafilatura
- Authentication and multi-user support
- Email sending integration (after human approval)
- Analytics dashboard with conversion tracking
- Webhook/notification system for approval events

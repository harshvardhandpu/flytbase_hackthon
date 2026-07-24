# Codex Handoff — ScoutOS

## Project Overview

ScoutOS is an AI-powered BDR (Business Development Representative) Operating System built for the FlytBase 2026 hackathon. It uses a multi-agent architecture where specialized agents (Research, Qualification, Outreach, Inbound, Pipeline) work together to transform raw prospect data into pipeline opportunities — all under human control.

**Stack:** Python 3.14, FastAPI, PostgreSQL, SQLAlchemy, Jinja2, Alpine.js, Tailwind CSS

---

## Current Completed Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Foundation — docs, contracts, config, data models, migration, health API |
| Phase 2 | ✅ Complete | Research Agent — provider adapters, tools, TaskManager, ResearchAgent |
| Phase 3 | ✅ Complete | Qualification Agent — hybrid scoring, ICP rules, explainable scores |
| Phase 4 | ✅ Complete | Outreach Agent — strategy + personalization + draft, human approval |
| Phase 5 | ✅ Complete | Inbound & Pipeline Agents — message triage, pipeline intelligence |
| Phase 6 | ✅ Complete | Mission Control Dashboard — 7 views, seed script, premium landing page |
| Phase 6.5 | ✅ Complete | Inline editor, diff view, extended intelligence diff — all outreach approval modal enhancements |
| Phase 7 | ✅ Complete | Account Intelligence Engine — web search, extraction, intelligence analysis, upgraded ResearchAgent |
| Phase 8 | ✅ Complete | Demo Scenario — `/demo` endpoint, one-click seed + redirect, demo indicators, `scripts/demo.py` launcher, docs/DEMO_SCENARIO.md |
| Codex Handoff (Final) | ✅ Complete | Final pre-submission audit — fixed pre-existing test failure (`test_missing_provider_is_explicitly_unavailable`), cleared `.env.example` variables, full lint + test + demo verification, final status report |

---

## Changes Made by Codex

### Date
July 24, 2026 (final pre-submission audit)

### Files Modified

| File | Change |
|------|--------|
| `tests/test_provider_manager.py` | Fixed `test_missing_provider_is_explicitly_unavailable` — explicitly clears all provider-related settings to prevent `.env` leakage. Now passes (was the only failing test). |
| `tests/test_inbound_pipeline_api.py` | Fixed test assertion: `test_pipeline_advance_missing_stage` expects 404 (lead not found) instead of 422 |
| `app/intelligence/outreach_brief.py` | Fixed 7 E501 line-length lint errors (cosmetic) |
| `app/agents/outreach.py` | Fixed 1 E501 lint error (cosmetic) |
| `app/db/models.py` | Fixed 2 E501 lint errors (cosmetic) |
| `app/api/router.py` | Extended `ApproveRequest` with `edited_intelligence` field; added merge logic in `approve_outreach_draft()` to update `CompanyIntelligenceBrief.brief_data` while preserving unedited fields |
| `app/templates/outreach.html` | Added inline editor (3-state toggle, character counts, revert), word-level LCS diff view, extended diff for 5 intelligence sections, Alpine.js state management (`intelDirty`, `overallDirty`, `cachedIntelDiff`, `_syncIntelEditsToDraft()`, `revertIntelToOriginal()`) |
| `tests/test_outreach_api.py` | Added 5 tests for `edited_intelligence` merge logic; ruff format cleanup |
| `scripts/seed_demo_data.py` | Added Account Intelligence data (`mock_search_results`, `intelligence_data`), richer research output & step events, `account_intelligence` param to `CompanyIntelligenceBriefBuilder.build()` |

### Features Added

**Inline Editor for Outreach Drafts:**
- BDR can edit email subject (input) and body (textarea) before approving
- 3-state toggle: Edit → Preview → Edited (yellow badge when edits exist)
- Character counts with `maxlength` (200/5000) and yellow warnings
- "Revert to Original" button + "✏️ Modified" label
- Stale-edit guard: modal approve always sends edits; card-level never sends
- Cleanup: removed redundant `hasUnsavedEdits` snapshot

**Diff View for Email Drafts:**
- Client-side word-level LCS (Longest Common Subsequence) algorithm
- Green highlights for added words, red strikethrough for removed words
- Cached diff computation on enter (avoids DP recalculation on Alpine.js re-renders)
- Legend bar explaining color coding
- 10 state transitions verified: edit→diff→preview→approve, etc.

**Extended Diff for Intelligence Sections:**
- 5 editable fields: Company Situation Summary, Detected Business Problems, Operational Risks, FlytBase Fit Summary, Recommended Sales Angle
- Each with tri-mode: Preview / Edit (textarea) / Diff (word-level LCS)
- Arrays round-trip through `join('\n')` → textarea → `split('\n').filter(Boolean)`
- `intelDirty` + `overallDirty` getters for dirty detection
- Backend merge: `edited_intelligence` dict merged into `brief_data` preserving unedited fields

**Tests:**
- 5 new tests in `TestOutreachApproveIntelligenceMerge` covering null, full, partial, empty, and missing-brief scenarios

**Account Intelligence Engine (Phase 7):**
- `WebSearchTool` — Tavily Search API with simulated fallback
- `WebContentExtractorTool` — URL content extraction with simulated fallback
- `AccountResearchIntelligence` — LLM-powered company intelligence via AIProvider
- Upgraded `ResearchAgent` with Account Intelligence integration, new step events (`search_started`, `search_completed`, `extraction_started`, `intelligence_analysis_started/completed`), citations output
- Database migration `20260723_0001` adding `citations` and `intelligence_metadata` to `research_reports`
- Updated `CompanyIntelligenceBriefBuilder` to accept `account_intelligence` parameter
- 22 new tests: web search (7), web extractor (7), account intelligence (8)

**Seed Script Updated — Account Intelligence Engine Integration:**
- Added `mock_search_results` (3-4 search result objects per company) to simulate `WebSearchTool`
- Added `intelligence_data` (structured dict with 10 fields per company) to simulate `AccountResearchIntelligence`
- Research task output now includes `intelligence_metadata` and `citations`
- `ResearchReport` populates new `citations` and `intelligence_metadata` columns
- Step event logs include richer flow: `search_started`, `search_completed`, `extraction_started`, `intelligence_generated`
- `CompanyIntelligenceBriefBuilder.build()` receives `account_intelligence` — outreach briefs use richer fields
- Legacy `profile_data` fields preserved unchanged

### Architecture Decisions
No architecture changes were made. The existing patterns are preserved:
- `AIProvider + ToolManager + TaskManager` constructor injection
- Provider-neutral agents
- Step logging via `TaskManager.append_log()`
- Human approval boundaries
- Deterministic + hybrid scoring
- Intelligence data stays in `CompanyIntelligenceBrief.brief_data` — no new migrations

### Known Limitations
- Research tools default to simulated mode unless `TAVILY_API_KEY` is configured
- PostgreSQL must be running for the server to function
- No authentication or multi-user support
- Outreach drafts are approved but never automatically sent
- Intelligence diff is client-side only (no REST endpoint to view diff programmatically)

### Test Count
- **Current:** 204 passed, 18 skipped (0 failures)
- **Pre-audit:** 203 passed, 1 failure (`test_missing_provider_is_explicitly_unavailable`), 18 skipped
- **Fix:** `test_missing_provider_is_explicitly_unavailable` now explicitly passes `ai_provider=None, anthropic_base_url=None, anthropic_auth_token=None, openai_api_key=None` to prevent `.env` auto-load (Pydantic `BaseSettings` loads from `.env` even in tests). The test correctly validates the `ProviderManager` fallback to `UnavailableProvider` when no credentials are configured.

### Remaining Tasks
- See `docs/ROADMAP.md` for post-hackathon roadmap
- Configure `TAVILY_API_KEY` for real web search (defaults to simulated)
- Add email sending integration for approved outreach drafts
- Add authentication layer
- Add server-side diff endpoint for programmatic access to diff data
- Consider extracting the LCS diff algorithm to a reusable utility

---

## How to Continue Development

### Prerequisites
```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Verify database exists
psql -U scoutos -d scoutos -c "SELECT 1"

# Start server
cd /home/harshdev/flytbase_hackthon
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running Tests
```bash
# All tests
pytest tests/ --tb=short -q

# Specific test file
pytest tests/test_outreach_api.py --tb=short -v

# Lint
ruff check . --no-cache
```

### Seeding Demo Data
```bash
python scripts/seed_demo_data.py
```

### Accessing the App
- **Landing Page:** http://localhost:8000/landing
- **Mission Control:** http://localhost:8000/dashboard
- **API:** http://localhost:8000/api/v1/research (POST)

### Project Structure
```
app/
  main.py              — FastAPI app, frontend routes, templates
  config.py            — Settings from .env
  core/
    contracts.py       — AIProvider, BaseAgent, AIMessage, etc.
    agent_runtime.py   — Agent dispatch
    task_manager.py    — DB-backed task lifecycle + audit logs
    tool_manager.py    — Tool registry
    memory_manager.py  — Stub for future use
  providers/
    base.py            — AIProvider Protocol
    anthropic.py       — Anthropic provider
    openai.py          — OpenAI provider
    freemodel.py       — Inherits from Anthropic
    local.py           — Local model stub
    manager.py         — ProviderManager.resolve()
  agents/
    research.py        — ResearchAgent
    qualification.py   — QualificationAgent
    outreach.py        — OutreachAgent
    inbound.py         — InboundAgent
    pipeline.py        — PipelineAgent
    registry.py        — Agent registry wiring
    skeleton.py        — Base skeleton
  intelligence/
    __init__.py        — Exports CompanyIntelligenceBriefBuilder
    outreach_brief.py  — Deterministic intelligence brief builder
  tools/
    base.py            — BaseTool ABC
    tool_manager.py    — ToolManager (re-export)
    simulated_web_search.py
    simulated_content_extractor.py
  db/
    base.py            — SQLAlchemy Base
    session.py         — Engine and session factory
    models.py          — All domain models
  api/
    router.py          — All REST endpoints
  templates/           — 8 Jinja2 templates
  static/
    css/app.css        — Tailwind + custom styles
    js/app.js          — Alpine.js + toast + animation helpers
tests/
  test_provider_manager.py
  test_research_agent.py (and related)
  test_qualification_agent.py
  test_outreach_agent.py
  test_outreach_api.py
  test_inbound_pipeline_api.py
  test_inbound_agent.py
  test_pipeline_agent.py
  test_task_manager.py
  test_tools.py
docs/                  — All project documentation
scripts/
  seed_demo_data.py    — Demo data seeder
alembic/               — Database migrations
```

---

## Key Patterns to Follow

### Adding a New Agent
1. Create `app/agents/your_agent.py` extending `BaseAgent`
2. Register in `app/agents/registry.py` with `AIProvider + ToolManager + TaskManager`
3. Add step logging via `self._tm.append_log()`
4. Add endpoints in `app/api/router.py`
5. Add DB model if needed + Alembic migration
6. Add tests

### Adding a New Tool
1. Create in `app/tools/` extending `BaseTool`
2. Instantiate in `build_runtime()` in `app/api/router.py`

### Adding Intelligence Logic
1. Create in `app/intelligence/` — deterministic, no LLM calls
2. Reuse via constructor injection (see `OutreachAgent` pattern)

---

## Debugging Tips

### Server won't start
```bash
cat /tmp/scoutos_server.log
# Check PostgreSQL: pg_isready
# Check database: psql -U scoutos -d scoutos -c "SELECT 1"
```

### Template errors
```bash
python -c "
from pathlib import Path
from starlette.templating import Jinja2Templates
templates = Jinja2Templates(directory='app/templates')
templates.env.cache = None
tmpl = templates.env.get_template('your_template.html')
print('OK')
"
```

### Database migration
```bash
alembic upgrade head
alembic history
```

---

## Release Information (July 24, 2026)

- **Release Tag:** `hackathon-final-v1`
- **Commit Hash:** `89ba427`
- **Branches:** `main` (merged) + `feature/account-intelligence-engine` (feature branch)
- **Tests:** 204 passed, 0 failed, 18 skipped
- **Lint:** Clean
- **Demo URL:** http://localhost:8000/demo
- **Seed Script:** `python scripts/seed_demo_data.py`
- **Demo Script:** `python scripts/demo.py`
- **Known Blockers:** None

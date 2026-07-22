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

## Codex Handoff — Final Verification ✅

**Completed:** July 21, 2026 (initial) / July 23, 2026 (updated)

**Delivered:** Project verification, DB fix, inline editor, diff view, extended intelligence diff, lint cleanup, documentation.

### What was built (July 23 update)
- Inline editor for outreach email drafts with editable subject/body, revert, character counts
- Word-level LCS diff view for email drafts
- Extended diff for all 5 intelligence sections (Company Intelligence + Pain Analysis)
- Backend merge logic for `edited_intelligence` in `ApproveRequest`
- 5 new tests for the merge logic

### What was verified
- PostgreSQL running and migrated to latest (`20260721_0001`)
- All **156 tests passing** (was 151)
- Lint clean (ruff pass)
- Server running on http://localhost:8000
- All views render without console errors
- Inline editor + diff + approve flow verified in browser

### Post-Hackathon Ideas
- Real web search API integration (replace simulated tools)
- Authentication and multi-user support
- Email sending integration (after human approval)
- Analytics dashboard with conversion tracking
- Webhook/notification system for approval events
- Export outreach history to CSV/PDF

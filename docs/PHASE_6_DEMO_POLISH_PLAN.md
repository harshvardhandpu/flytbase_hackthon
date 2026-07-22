# Phase 6 — Mission Control & Demo Polish Plan

> **Status:** Plan ready for review  \
> **Depends on:** Phase 5 (Inbound + Pipeline Agents)  \
> **Deadline:** July 25, 2026 (hackathon demo)  \
> **Est. effort:** 3-4 days

---

## Overview

Phase 6 ships a polished **Mission Control dashboard** — a single-page frontend that ties all five agent phases together into a coherent demo experience. Every backend capability built in Phases 1-5 gets a visual face: research, qualification, outreach (with approve/reject), inbound messages, pipeline Kanban, and agent activity traces.

The guiding principle: **the demo must tell a story.** A BDR sits down, researches a company, qualifies it, generates an outreach draft, approves it, processes an inbound reply, and monitors the pipeline — all within a single UI, with visible agent intelligence at every step.

---

## 1. Frontend Architecture

### Stack recommendation

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Rendering** | FastAPI Jinja2Templates + static files | No build tooling, no npm. Ships as pure Python. Zero backend changes needed. |
| **CSS** | Tailwind CSS via CDN | Rapid prototyping, responsive, clean defaults. No build step. |
| **JS** | Vanilla JS + Alpine.js via CDN | Reactive components without a framework. Minimal learning curve. |
| **Icons** | Heroicons via SVG | Consistent, recognisable icon set. |
| **Charts** | Chart.js via CDN | Lightweight, good-enough charts for pipeline metrics. |

**Why not React/Svelte/Vue?** The hackathon timeline (4 days) doesn't allow for a separate frontend build pipeline, bundler config, API client generation, and state management. Jinja2 + Alpine.js delivers a polished demo with zero build step — the UI is part of the FastAPI process.

**Alternative if time permits:** Embed a standalone Preact or Svelte app served as static files. This is a stretch goal — only pursue if the Jinja2 approach is finished early.

### File layout

```text
app/
├── main.py                 # ← Add mount for static files + templates
├── templates/
│   ├── base.html           # ← Layout shell (nav, sidebar, footer)
│   ├── dashboard.html      # ← Mission Control overview
│   ├── leads.html          # ← Lead intelligence list
│   ├── lead_detail.html    # ← Single lead: research + qual + outreach
│   ├── outreach.html       # ← Outreach drafts with approve/reject
│   ├── pipeline.html       # ← Pipeline Kanban board
│   ├── inbound.html        # ← Inbound message queue
│   ├── activity.html       # ← Agent activity / task logs
│   └── settings.html       # ← ICP config, provider settings
├── static/
│   ├── css/
│   │   └── app.css         # ← Minimal custom styles (mostly Tailwind)
│   └── js/
│       ├── alpine.js        # ← Alpine.js (served locally or CDN)
│       └── app.js           # ← Custom JS: API calls, interactions
```

### Template structure

`base.html` provides the layout shell:

```
┌─────────────────────────────────────────────────────┐
│  🔭 ScoutOS Mission Control          [env] [user]   │
├────────┬────────────────────────────────────────────┤
│        │                                            │
│ Nav    │  Main Content Area                         │
│ ─────  │                                            │
│ 📊     │  (Each view rendered as a separate         │
│   Dash │   Jinja2 template extending base.html)     │
│ │      │                                            │
│ 👥     │                                            │
│   Leads │                                            │
│ │      │                                            │
│ ✉️     │                                            │
│   Outreach │                                         │
│ │      │                                            │
│ 🚀     │                                            │
│   Pipeline │                                         │
│ │      │                                            │
│ 📨     │                                            │
│   Inbound │                                          │
│ │      │                                            │
│ ⚡     │                                            │
│   Activity │                                         │
│ │      │                                            │
│ ⚙️     │                                            │
│   Settings                                           │
│        │                                            │
└────────┴────────────────────────────────────────────┘
```

---

## 2. Views (In Priority Order)

### P0 — Mission Control Dashboard (`/`)

The landing page that tells the demo story at a glance.

**Top stats bar:**
- Total leads in pipeline
- HOT leads (score >= 70)
- Pending approval (outreach drafts awaiting review)
- Stale leads requiring attention (stage_health = "stale" | "critical")

**Recent activity feed:**
- Last 10 agent task completions across all phases
- Each entry shows: agent type, company/lead name, status, timestamp
- Color-coded by agent type (research=blue, qualification=purple, outreach=green, inbound=orange, pipeline=teal)

**Pipeline snapshot:**
- Mini Kanban showing lead counts per stage
- Color-coded bars: green=healthy, yellow=stale, red=critical

**Quick actions:**
- "Research a new company" — opens a modal with company name/domain input
- "Process inbound message" — opens a modal with message form
- "Review pending approvals" — jumps to outreach view

### P0 — Lead Intelligence (`/leads` / `/leads/{lead_id}`)

**List view (`/leads`):**
- Table with columns: Company, Contact, Status, Score, Priority, Stage Health, Days in Stage, Last Activity
- Sortable by score, priority, days in stage
- Filterable by stage, health, priority
- Click a row → detail view

**Detail view (`/leads/{lead_id}`):**
Four-card layout showing the full BDR pipeline for one lead:

| Card | Content | Source API |
|------|---------|------------|
| **Company Profile** | Name, domain, industry, employee count, location, description | `GET /api/v1/reports/{report_id}` |
| **Qualification** | Overall score (gauge visualization), component scores (ICP match, buying signal, company fit), priority badge (HOT/WARM/COLD), reasons list, risks list, BDR action | `GET /api/v1/qualification/{task_id}` |
| **Outreach Draft** | Strategy (channel, urgency), personalization (hook, pain point, value prop), email draft (subject, body preview), approval status with approve/reject buttons | `GET /api/v1/outreach/{task_id}` |
| **Pipeline Position** | Current stage, stage health badge, days in stage, stagnation risk, recommended next action | `GET /api/v1/pipeline/{task_id}` |

### P0 — Outreach Drafts (`/outreach`)

**Queue view:**
- Cards for each draft, sorted by creation date
- Status badges: pending_approval (yellow), approved (green), rejected (red)
- Each card shows: company name, subject line preview, urgency badge, created date
- "pending_approval" cards have inline Approve / Reject buttons

**Detail modal (click card):**
- Full email preview (rendered HTML, not raw text)
- Strategy panel: recommended channel, urgency, reasoning
- Personalization panel: company hook, detected pain point, value prop
- Follow-up suggestion
- Approve with reviewer name / Reject with reason

**Bulk actions:**
- Select multiple pending drafts and approve/reject in batch (stretch)

### P0 — Pipeline Kanban (`/pipeline`)

**Kanban board:**
- Columns for each active pipeline stage (new → researching → qualified → outreach → meeting_scheduled → negotiation → closed_won → closed_lost)
- Cards for leads in each stage, showing: company name, score (if qualified), days in stage
- Color-coded health indicator on each card: green=healthy, yellow=stale, red=critical

**Interactions:**
- Click a card → open lead detail
- Inline "Advance" button on each card → calls `POST /api/v1/pipeline/{lead_id}/advance` with next stage

**Stage health bars:**
- Below each column header: bar showing healthy/stale/critical count for that stage

### P1 — Inbound Messages (`/inbound`)

**Queue view:**
- List of inbound messages sorted by received_at descending
- Each row shows: from_email, subject preview, intent badge, sentiment icon, urgency indicator, status
- Click → expand to full analysis

**Detail view (expandable):**
- Raw message: from, subject, body (formatted)
- AI analysis: intent, sentiment, urgency, confidence score
- Extracted details: topics, pain points, interest signals, contact role
- Suggested reply preview (if generated)
- Approve / Reject buttons for pending_review messages

### P1 — Agent Activity (`/activity`)

**Task feed:**
- Chronological list of all agent tasks
- Filter by agent type (research, qualification, outreach, inbound, pipeline)
- Filter by status (completed, failed, waiting_for_approval)

**Task detail (expandable):**
- Step-by-step log viewer showing each `append_log` event
- Structured data shown as JSON (expandable)
- Error events highlighted in red
- Duration between steps (nice-to-have)

### P2 — Settings (`/settings`)

- ICP configuration editor (industries, employee range, locations)
- Provider status display (which provider is active, model name)
- Pipeline stage management (stretch — not needed for demo)

---

## 3. API Extensions Required

The Phase 1-5 API has all the data needed. Two convenience endpoints would simplify the frontend:

| Endpoint | Purpose | Why needed |
|----------|---------|------------|
| `GET /api/v1/leads/dashboard` | Returns aggregate stats for the dashboard top bar | Avoids N+1 queries from the frontend. Returns: total_leads, hot_leads, pending_approvals, stale_leads, recent_activity[]. |
| `GET /api/v1/leads/{lead_id}/full` | Returns all data for a single lead (research + qual + outreach + pipeline) in one call | The lead detail view needs 4 API calls currently. This collapses to 1. |

**These are optional.** The frontend can call existing endpoints directly. The dashboard and detail views just load slower. Add these only if time permits.

---

## 4. Demo Script

The July 25 demo should follow a single lead from discovery to approval, showing agent intelligence at every step. Here is the script:

### Scene 1: Research a new company (30 seconds)

1. BDR lands on Mission Control dashboard
2. Clicks "Research a new company" → modal opens
3. Enters "SkyGrid Inc." and "skygrid.io" → submits
4. UI shows task spinner → 2 seconds later: "Research completed"
5. Company profile appears with industry (Drone Services), employees (~200), location (Austin, TX), business signals, pain points

**What the demo proves:** Research Agent works end-to-end. The LLM planned queries, executed searches, extracted content, and synthesised a structured report.

### Scene 2: Qualify the lead (20 seconds)

1. BDR clicks "Qualify this lead" on the research result
2. UI shows scoring animation → scores appear: 91/100 HOT
3. ICP match, buying signal, company fit scores visible
4. Reasons for the score are displayed: "+ Industry 'Drone Services' matches ICP", "+ Company size 200 within ICP range"
5. Risks listed: "- No public buying signal detected"

**What the demo proves:** Qualification Agent's hybrid scoring works — deterministic rules plus LLM signal evaluation.

### Scene 3: Generate outreach draft (25 seconds)

1. BDR clicks "Generate outreach" → uses research + qualification
2. Strategy appears: email, urgency=Immediate
3. Personalization intelligence: hook referencing SkyGrid's EU expansion, detected pain point about manual pilot scheduling
4. Email draft preview with subject, body, follow-up suggestion
5. Status: Pending Approval — "Awaiting your review"

**What the demo proves:** Outreach Agent's 3-stage workflow (strategy → personalization → draft). Human approval boundary is enforced — no auto-send.

### Scene 4: Approve the draft (15 seconds)

1. BDR navigates to Outreach view
2. Sees the pending draft card with Approve / Reject buttons
3. Clicks Approve → enters name "Harsh" → submits
4. Status changes to Approved → history record created
5. "Draft approved. Ready to send (send integration coming soon)."

**What the demo proves:** Human approval boundary works. Historical record created for audit.

### Scene 5: Process an inbound reply (20 seconds)

1. BDR navigates to Inbound view
2. Clicks "Process message" → pastes a simulated reply from SkyGrid
3. Message: "Thanks for reaching out! We'd love to schedule a demo next week."
4. AI analysis: intent=meeting_request, sentiment=positive, urgency=high
5. Suggested reply generated → Pending Review

**What the demo proves:** Inbound Agent classifies intent/sentiment/urgency and generates a contextual reply.

### Scene 6: Pipeline overview (15 seconds)

1. BDR navigates to Pipeline view
2. Kanban board shows SkyGrid in "Outreach" stage (after qualification)
3. After inbound message, pipeline evaluation shows: health=healthy, risk=low
4. Recommendation: "Advance to meeting_scheduled"

**What the demo proves:** Pipeline Agent aggregates data from all phases and recommends next actions. The full lifecycle is visible.

### Total demo time: ~2 minutes

---

## 5. Implementation Order

### Micro-phased schedule (4 days)

| Day | Focus | Components | Est. effort |
|-----|-------|------------|-------------|
| **1** | Foundation + Dashboard | FastAPI setup, Jinja2, static files, base template, nav, dashboard stats + activity feed | 5h |
| **2** | Leads + Outreach | Leads list, lead detail (4 cards), outreach draft queue + approve/reject | 8h |
| **3** | Pipeline + Inbound | Pipeline Kanban (no drag-drop, click + advance button), activity endpoint, inbound queue | 8h |
| **4** | Polish + Data | Loading skeletons, error banners, transitions, seed-data script, demo rehearsal | 6h |

**Total: ~27h build + 7h buffer = 34h (4 days)** — trimmed from 37h by removing drag-drop Kanban, Settings page, and convenience endpoints.

### Build order (P0 only — Settings and convenience endpoints are dropped)

| # | Component | Est. effort | Why this order |
|---|-----------|-------------|----------------|
| 1 | FastAPI setup: mount Jinja2 templates (`app/templates/`), static files (`app/static/`), add jinja2 to deps, base template + nav | 2h | Foundation for everything else. Note: `templates/` and `static/` directories do NOT get `__init__.py` files. |
| 2 | Dashboard view (stats + activity feed) | 3h | Landing page — first thing demo sees |
| 3 | Leads list + detail view (research, qual, outreach cards) | 8h | Core of the demo — shows Phases 2-4 data |
| 4 | Outreach drafts view (approve/reject UI) | 4h | Shows human approval boundary — key demo moment |
| 5 | Pipeline Kanban (simplified — click + advance button, no drag-drop) | 5h | Shows Phase 5 pipeline intelligence |
| 6 | Inbound messages view | 4h | Shows Phase 5 inbound processing |
| 7 | Loading states + error handling (skeletons, spinners, error banners) | 2h | Every view needs this |
| 8 | Activity / task log viewer | 3h | Shows agent step-by-step execution (P1 if tight) |
| 9 | Seed-data script + demo rehearsal | 3h | Populates DB with realistic demo data |

**Total P0: ~34 hours** (27h build + 7h buffer).

---

## 6. Design System

### Colors

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#0f172a` (slate-900) | Dark background for a "Mission Control" feel |
| Surface | `#1e293b` (slate-800) | Cards, sidebar, modals |
| Surface hover | `#334155` (slate-700) | Hover states |
| Primary | `#06b6d4` (cyan-500) | Primary actions, active nav, links |
| Primary hover | `#22d3ee` (cyan-400) | Button hovers |
| Success | `#22c55e` (green-500) | Approved, healthy, HOT |
| Warning | `#eab308` (yellow-500) | Pending, stale, medium urgency |
| Danger | `#ef4444` (red-500) | Rejected, critical, high urgency |
| Text primary | `#f8fafc` (slate-50) | Headings, primary text |
| Text secondary | `#94a3b8` (slate-400) | Body text, labels |
| Text muted | `#64748b` (slate-500) | Timestamps, metadata |

### Typography

- Font: Inter (via Google Fonts CDN)
- Scale: 12 / 14 / 16 / 18 / 24 / 30 / 36 px
- Headings: font-semibold
- Body: font-normal leading-relaxed
- Code/monospace: font-mono (for JSON, step data)

### Component patterns

**Stat card:**
```html
<div class="bg-slate-800 rounded-lg p-4 border border-slate-700">
  <div class="text-slate-400 text-sm">Label</div>
  <div class="text-3xl font-semibold text-slate-50 mt-1">Value</div>
  <div class="text-xs text-slate-500 mt-1">Subtitle or change</div>
</div>
```

**Badge:**
```html
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-800">
  HOT
</span>
```

**Activity feed item:**
```html
<div class="flex items-start gap-3 py-3 border-b border-slate-700/50">
  <div class="w-2 h-2 mt-2 rounded-full bg-cyan-500 flex-shrink-0"></div>
  <div class="flex-1 min-w-0">
    <p class="text-sm text-slate-200">Research completed for <span class="font-medium">SkyGrid Inc.</span></p>
    <p class="text-xs text-slate-500 mt-0.5">2 minutes ago</p>
  </div>
  <span class="text-xs text-green-400 font-medium">completed</span>
</div>
```

**Pipeline card (Kanban):**
```html
<div class="bg-slate-800 rounded-lg p-3 border border-slate-700 cursor-pointer hover:border-slate-500 transition-colors">
  <div class="flex items-center justify-between">
    <h4 class="text-sm font-medium text-slate-200">SkyGrid Inc.</h4>
    <span class="w-2 h-2 rounded-full bg-green-500"></span>
  </div>
  <div class="flex items-center gap-2 mt-2">
    <span class="text-xs bg-purple-900/30 text-purple-400 px-1.5 py-0.5 rounded">91</span>
    <span class="text-xs text-slate-500">14 days</span>
  </div>
</div>
```

---

## 7. Data Flow

### How the frontend gets data

1. **Page load** → Jinja2 renders the shell (nav + layout) with empty content areas
2. **Alpine.js init** → Fetches data from API endpoints using `fetch()` + `await`
3. **Data populates** → Alpine.js `x-data` properties update → DOM re-renders reactively
4. **User actions** (approve, reject, research) → `fetch()` POST/PUT to API → Alpine.js refreshes affected sections

### Minimal backend changes required

The Phase 1-5 API already exposes most of what the frontend needs. The frontend calls:

| View | API calls |
|------|-----------|
| Dashboard | `GET /api/v1/pipeline/leads` + `GET /api/v1/outreach/{task_id}` for pending counts |
| Leads list | `GET /api/v1/pipeline/leads` |
| Lead detail | `GET /api/v1/reports/{report_id}` + `GET /api/v1/qualification/{task_id}` + `GET /api/v1/outreach/{task_id}` |
| Outreach | `GET /api/v1/outreach/{draft_id}` + approve/reject POSTs |
| Pipeline | `GET /api/v1/pipeline/leads` + advance POST |
| Inbound | `GET /api/v1/inbound/{task_id}` + approve/reject POSTs |
| Activity | `GET /api/v1/outreach/{task_id}` logs... (or new endpoint) |

### New endpoint needed: Activity feed

The existing API has per-task logs (`AgentLog`), but no global activity feed. Add:

**`GET /api/v1/activity`** 
- Query params: `limit` (default 20), `agent_type` (optional filter), `status` (optional filter)
- Returns: list of recent tasks with summary + log count

**Implementation:** Query `agent_tasks` ordered by `updated_at DESC` with optional filters.

---

## 8. Backend Changes Required

### Minimal (P0)

1. **`app/main.py`** — Mount Jinja2 templates + static files
2. **`pyproject.toml`** — Add `jinja2` to dependencies (if not already present)
3. **`GET /api/v1/activity`** — New endpoint for activity feed
4. **`app/templates/`** + **`app/static/`** — All frontend files

### Optional (P1/P2)

5. **`GET /api/v1/leads/dashboard`** — Aggregate stats endpoint
6. **`GET /api/v1/leads/{lead_id}/full`** — Lead bundle endpoint

### No changes needed

- **No new DB models** — all data exists in Phase 1-5 tables
- **No new migrations** — data layer is complete
- **No new agents** — all five agents are implemented
- **No provider changes** — AIProvider contract is unchanged

---

## 9. Testing Strategy

### Frontend verification (manual, before demo)

| Check | How to verify |
|-------|---------------|
| Dashboard loads with real stats | Navigate to `/` — stats cards populate |
| Lead list renders | Navigate to `/leads` — table shows leads |
| Lead detail shows all phases | Click a lead — 4 cards render with data |
| Outreach approve works | Navigate to `/outreach` → click Approve → status changes |
| Pipeline Kanban renders | Navigate to `/pipeline` — columns show leads |
| Inbound message processes | Navigate to `/inbound` → process message → analysis appears |
| Activity feed shows tasks | Navigate to `/activity` — chronological list appears |
| All pages on mobile | Resize browser to 375px width — layout adapts |

### Backend tests

| Test | What it verifies |
|------|------------------|
| `test_activity_endpoint` | `GET /api/v1/activity` returns list with expected fields |
| `test_activity_filter` | Filtering by agent_type returns correct subset |
| `test_activity_limit` | Limit parameter works correctly |

---

## 10. Risk and Mitigations

| Risk | Mitigation |
|------|-----------|
| Not enough time to build all views | Prioritize P0 views (Dashboard, Leads, Outreach, Pipeline). Drop Inbound and Activity if needed. The demo still tells a complete story with 4 views. |
| Jinja2 + Alpine.js feels unpolished | Focus on visual polish: dark theme, smooth transitions, loading skeletons, consistent spacing. A well-designed Jinja2 app can look as good as a framework SPA. |
| API is slow with N+1 queries | The dashboard and lead detail views make multiple API calls. Use Promise.all() for parallel fetches. Add dashboard convenience endpoint if needed. |
| No real data to display | The backend has simulated data. Run the full demo flow (research → qualify → outreach → inbound) before the demo to populate the database with realistic data. |
| Tailwind CDN fails offline | Download Tailwind CSS file and serve from `app/static/css/` for offline reliability. |
| Alpine.js learning curve | Keep components simple. Use `x-data` + `x-init` + `x-text` patterns. Avoid complex expressions. |

---

## 11. What Future Phases Reuse

| Component | Reused by |
|-----------|-----------|
| Jinja2 base template + navigation | Future admin panels, onboarding flows |
| Dashboard stat cards + activity feed | Any analytics or monitoring page |
| Pipeline Kanban component | CRM integration views |
| Outreach approve/reject UI | Auto-reply approval workflows |
| Agent activity viewer | Debugging, auditing, compliance |
| Lead detail composite view | Sales rep daily workflow |

---

## 12. Architectural Contract Checks

- ✅ **No agents modified** — Phase 6 adds frontend only, no agent logic changes
- ✅ **No provider changes** — UI doesn't touch AIProvider
- ✅ **No DB schema changes** — all data exists in Phase 1-5 models
- ✅ **No new migrations** — existing tables have all the data
- ✅ **No auto-send** — frontend calls existing approve/reject endpoints; agent's `requires_human_approval` remains the guard
- ✅ **Existing tests unaffected** — frontend is additive, no backend test changes
- ✅ **Existing API unchanged** — frontend consumes existing endpoints; new endpoints are additive

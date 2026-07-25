# ScoutOS — Demo Scenario

> FlytBase Hackathon 2026  
> 3-Minute Judge Demonstration

---

## 1. The Story

**SkyGrid Inc.** is an enterprise drone fleet management company that has just raised a $40M Series B to expand into the EU market. They're hiring aggressively, scaling their operations, and facing the operational challenges that come with rapid growth.

ScoutOS demonstrates how five AI agents work together to:
1. **Research** SkyGrid's business situation
2. **Qualify** them as a HOT lead (score: 91/100)
3. **Generate** a personalized outreach email
4. **Process** an inbound reply from their Head of Operations
5. **Track** them through the pipeline to "Meeting Scheduled"

---

## 2. The 3-Minute Walkthrough

### Minute 1: Landing → Dashboard → SkyGrid Detail

| Time | Action | What Judge Sees |
|------|--------|-----------------|
| 0:00 | Navigate to `/demo` | Demo scenario introduction with agent pipeline flow |
| 0:05 | Click **"Launch Demo Mission"** | Data seeds, auto-redirects to Dashboard |
| 0:15 | **Dashboard** loads | **Stats bar**: 5 total leads, 2 HOT (SkyGrid=91, DroneFleet=85) |
| 0:20 | | **Pipeline Snapshot**: 8 stages, leads in each column |
| 0:25 | | **Activity Feed**: Agent execution history with timestamps |
| 0:35 | Click SkyGrid lead → **Lead Detail** | **🎯 Demo Account** indicator badge |
| 0:40 | | **Card 1 — Company Profile**: Industry, employees (320), location, business signals |
| 0:45 | | **Card 2 — Qualification**: Score gauge (91), ICP (95), Buying (88), Fit (90) |

**Key talking point:** "The qualification card shows hybrid scoring — deterministic rules (industry, size, location) combined with AI evaluation of buying signals and pain points."

### Minute 2: Lead Detail → Outreach → Inbound

| Time | Action | What Judge Sees |
|------|--------|-----------------|
| 1:00 | Scroll to **Card 3 — Outreach Draft** | Approved email to Sarah Chen |
| 1:05 | | Strategy: email channel, "This week" urgency |
| 1:10 | | Hook: references Series B and EU expansion |
| 1:15 | Navigate to **Outreach** page | 3 drafts: SkyGrid (approved), DroneFleet (pending), AeroVista (pending) |
| 1:20 | Click SkyGrid draft → **Modal** | Full intelligence brief: Company Situation, Pain Analysis, FlytBase Fit |
| 1:25 | | Inline editor + diff view for BDR edits before approval |
| 1:30 | Navigate to **Inbound** page | Sarah Chen's reply: "Hi Jane, we're interested..." |
| 1:35 | | **Intent detection**: `meeting_request` with 0.92 confidence |
| 1:40 | | **Sentiment**: positive, **Urgency**: high |
| 1:45 | | Suggested reply ready for human review |
| 1:50 | Optional: **New Inbound Email** → `/inbound/new` | Manual simulation form (no mailbox required) |
| 1:55 | | Submit → analysis page shows intent, score, recommended action |

**Key talking point:** "The human approval boundary ensures no message is ever auto-sent. Every draft requires a BDR to review, edit if needed, and explicitly approve. Judges can also simulate a fresh inbound email at `/inbound/new` without external email integrations."

### Minute 3: Pipeline → Activity → Architecture

| Time | Action | What Judge Sees |
|------|--------|-----------------|
| 2:00 | Navigate to **Pipeline** | Kanban board with 8 stages |
| 2:05 | | **SkyGrid** is in "Meeting Scheduled" (green) — 🎯 Demo indicator |
| 2:10 | | **DroneFleet** in "Outreach" — HOT lead |
| 2:15 | | **AeroVista** in "Outreach" — WARM lead |
| 2:20 | | **AirMap** in "Qualified" — WARM |
| 2:25 | Navigate to **Activity** | Complete audit log: research → qualification → outreach → inbound → pipeline |
| 2:30 | | Each agent execution shows step-level events |
| 2:35 | Return to **Dashboard** or open **Demo page** | Summary view of all capabilities |
| 3:00 | Q&A | Discuss architecture, provider neutrality, extensibility |

---

## 3. Agent Flow Diagram

```
SkyGrid Inc. (Input)
       │
       ▼
┌─────────────────┐
│  Research Agent │  Company profile, tech stack, pain points
│  (Web Search)   │  Industry: Drone Technology, Employees: 320
└────────┬────────┘
         │ ResearchReport
         ▼
┌─────────────────┐
│ Qualification   │  Overall: 91  │  ICP: 95
│    Agent        │  Buying: 88   │  Fit: 90
└────────┬────────┘  Priority: HOT │ Urgency: This week
         │ QualificationResult
         ▼
┌─────────────────┐
│  Outreach Agent │  Strategy → Personalization → Draft
│  (LLM)          │  Channel: email | Subject: "Scaling..."
└────────┬────────┘  Status: approved (after human review)
         │ OutreachDraft
         ▼
┌─────────────────┐
│   Inbound Agent │  "Hi Jane, interested in demo..."
│  (LLM)          │  Intent: meeting_request (0.92)
└────────┬────────┘  Sentiment: positive | Urgency: high
         │ InboundMessage
         ▼
┌─────────────────┐
│ Pipeline Agent  │  Stage: meeting_scheduled ✅
│  (Deterministic)│  Health: healthy | Risk: low
└─────────────────┘
```

---

## 4. Data Flow

```
seed_demo_data.py
    │
    ├── Companies (5) ─── SkyGrid, AeroVista, DroneFleet, AirMap, PrecisionAg
    ├── ICP Config ────── Industries, size range, locations, tech signals
    ├── Pipeline Stages ── 8 stages from New → Closed Won/Lost
    │
    ├── Research Tasks ── With Account Intelligence enriched fields
    ├── Research Reports ── Citations, intelligence_metadata
    ├── Qualification ──── Hybrid scoring (deterministic + AI)
    ├── Outreach Drafts ── Strategy, personalization, email body
    ├── Company Intelligence Briefs ── Per draft
    ├── Inbound Messages ── SkyGrid (2 messages), DroneFleet (1)
    ├── Pipeline Status ─── One current status per lead
    ├── Conversations ───── SkyGrid conversation record
    └── Agent Logs ──────── Step-level audit trail for each task
```

### Key Data Points for SkyGrid

| Field | Value | Significance |
|-------|-------|--------------|
| Company | SkyGrid Inc. | The demo anchor company |
| Industry | Drone Technology | Direct ICP match |
| Employees | 320 | Within ICP range (30-1000) |
| Location | San Francisco, CA | US — target region |
| Score | 91/100 | HOT priority (≥70) |
| Pipeline | Meeting Scheduled | Late-stage demo success |
| Inbound | Sarah Chen (COO) | Realistic positive reply |

---

## 5. Judge Talking Points

### Architecture Strengths
1. **Provider-Neutral AI** — All 5 agents use the same `AIProvider` interface. Swap between Anthropic, OpenAI, FreeModel, or local with a config change.
2. **Tool Abstraction** — Every agent capability is a registered `BaseTool`. Simulated tools for demo, real Tavily/HTTP adapters for production.
3. **Human Approval Boundary** — No auto-sending. Every outreach message requires BDR review, edit, and explicit approval.

### What Makes ScoutOS a Platform (Not a Chatbot)
- 5 specialized agents with distinct responsibilities
- Database-backed task lifecycle (status, logs, outputs)
- Structured BDR-focused output (not general-purpose chat)
- Hybrid scoring (deterministic rules + AI evaluation)
- Complete audit trail for every agent step

### Demo-Specific Highlights
- **Account Intelligence Engine**: Enriches research with structured company situation, business problems, operational risks, growth signals, and industry incidents — all with citations
- **Inline Editor + Diff View**: BDRs can edit drafts and intelligence before approval, with word-level diff showing exactly what changed
- **Dashboard Skeleton Loading**: Professional UX with loading states and animated stat counters
- **All Systems Nominal**: Green indicator in sidebar showing system health

---

## 6. How to Run the Demo

### One-Command Launcher (Recommended)

The fastest way to start the demo:

```bash
python scripts/demo.py
```

This script:
1. Checks Python version, virtual environment, `.env` file, and PostgreSQL connection
2. Runs Alembic migrations (`alembic upgrade head`)
3. Seeds demo data (`scripts/seed_demo_data.py`)
4. Verifies the server is running (`GET /health`)
5. Prints demo instructions with the interactive flow

If the server isn't running, it prints the exact command to start it.

Exit codes:
- `0` — Demo ready
- `1` — Environment issue (missing Python, venv, DB, etc.)

### Manual Steps

```bash
# 1. Start the server
cd /home/harshdev/flytbase_hackthon
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 2. Open the demo page
#    Browser → http://localhost:8000/demo

# 3. Click "Launch Demo Mission"
#    - Seeds demo data into PostgreSQL
#    - Redirects to Dashboard

# 4. Walk through the 7 views:
#    Dashboard → Leads → Lead Detail → Outreach → Inbound → Pipeline → Activity

# Alternative: Pre-seed data
python scripts/seed_demo_data.py
# Then navigate directly to http://localhost:8000/dashboard
```

---

## 7. Test Coverage

| Test Area | Count | Status |
|-----------|-------|--------|
| Unit tests | 185 | ✅ Passing |
| Real provider integration tests | 12 | ✅ Skipped (needs API key) |
| Pre-existing known failure | 1 | ✅ Unrelated (provider-manager test) |
| Lint (ruff) | 0 errors | ✅ Clean |

---

## 8. Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Backend                     │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │AIProvider│  │ToolManager│  │TaskManager│          │
│  │ (Neutral)│  │ (Plugins) │  │ (Lifecycle)│         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
│  ┌────┴──────────────┴──────────────┴────┐            │
│  │          Agent Registry               │            │
│  │  Research│Qualify│Outreach│Inbound│Pipeline │     │
│  └─────────────────────────────────────────┘          │
│       │                                              │
│  ┌────┴────────────────────────────────────────────┐  │
│  │           Mission Control UI (Jinja2 + Alpine)   │  │
│  │   Dashboard │ Leads │ Outreach │ Inbound        │  │
│  │   Pipeline │ Activity │ Landing │ Demo          │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

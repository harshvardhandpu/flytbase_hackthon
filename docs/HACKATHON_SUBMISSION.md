# ScoutOS — FlytBase Hackathon 2026 Submission

> **AI-Powered BDR Operating System**  
> Multi-agent prospect research, qualification, outreach, inbound handling, and pipeline intelligence — all under human control.

---

## Project Overview

ScoutOS is an AI-native BDR (Business Development Representative) Operating System that transforms raw prospect data into pipeline opportunities. Five specialized AI agents work together in a coordinated pipeline — research, qualify, draft outreach, handle inbound replies, and track pipeline movement — while keeping humans in control of every consequential action.

**Stack:** Python 3.14, FastAPI, PostgreSQL, SQLAlchemy, Jinja2, Alpine.js, Tailwind CSS

---

## Problem

Business development representatives face a set of interconnected challenges that slow them down and reduce effectiveness:

| Problem | Impact |
|---------|--------|
| **Manual research** | BDRs spend hours manually searching for company information, funding news, technology signals, and pain points — time that could be spent on conversations |
| **Generic outreach** | Without structured intelligence, outreach becomes templated and low-relevance, resulting in poor response rates |
| **Scattered pipeline info** | Pipeline data lives across spreadsheets, emails, notes, and CRM fields — no single view of where each deal stands |
| **Slow inbound handling** | Inbound messages sit unanswered while BDRs triage manually, risking prospect disengagement |
| **No audit trail** | Without structured logging, it's impossible to understand why decisions were made or what signals were considered |
| **Lost context between phases** | Research insights don't flow into qualification, which doesn't feed outreach — each phase starts from scratch |

---

## Solution

### Agent Workflow

```
Company/Domain Input
        │
        ▼
┌────────────────────┐
│   Research Agent   │  → Company profile, industry, tech stack
│  (Web Search + LLM) │  → Pain points, growth signals, buying signals
└────────┬───────────┘  → Account Intelligence with citations
         │
         ▼
┌────────────────────┐
│     Account        │  → Company situation summary
│  Intelligence      │  → Business problems detected
│  Engine            │  → Operational risks identified
└────────┬───────────┘  → Growth & buying signals
         │               → Industry incidents
         ▼
┌────────────────────┐
│ Qualification Agent│  → Hybrid scoring (deterministic + AI)
│  (Rules + LLM)      │  → ICP match: 0-100
└────────┬───────────┘  → Buying signal score
         │               → Company fit score
         ▼               → Priority: HOT / WARM / COLD
┌────────────────────┐
│   Outreach Agent   │  → Strategy (channel, urgency, reasoning)
│  (LLM + Templates) │  → Personalization intelligence
└────────┬───────────┘  → Email draft with follow-up
         │               → ❌ NOT auto-sent
         ▼
┌────────────────────┐
│   Human Approval   │  ← BDR reviews, edits, approves/rejects
│   Boundary         │  → Immutable audit trail
└────────┬───────────┘
         │
┌────────────────────┐
│   Inbound Agent    │  → Intent classification (meeting request, etc.)
│  (LLM + Rules)      │  → Sentiment analysis
└────────┬───────────┘  → Urgency assessment
         │               → Suggested reply with approval
         ▼
┌────────────────────┐
│  Pipeline Agent    │  → Stage health: healthy / stale / critical
│  (Rules + LLM)      │  → Stagnation risk
└────────────────────┘  → Next best action recommendation
```

### Key Differentiators

#### 1. Multi-Agent Architecture (Not a Chatbot)
ScoutOS isn't a single LLM wrapped in a chat interface. It's five specialized agents, each with distinct responsibilities, tools, and output structures. Research doesn't generate emails — it generates structured reports. Qualification doesn't chat — it computes scores. This creates a composable, debuggable system.

#### 2. Human-in-the-Loop Approval
No outreach message is ever auto-sent. Every draft requires explicit BDR review, optional inline editing with diff visualization, and deliberate approval. This preserves the human relationship while leveraging AI for preparation.

#### 3. Account Intelligence Before Outreach
Before the Outreach Agent drafts a message, the Account Intelligence Engine has already analyzed:
- Company situation and growth trajectory
- Detected business problems
- Operational risks of inaction
- Relevant industry incidents
- Why FlytBase specifically fits

The BDR sees all of this on the approval screen before deciding to send.

#### 4. Provider-Neutral AI Design
All five agents use the `AIProvider` interface — never import concrete providers. Swap between Anthropic, OpenAI, FreeModel, or a local model with a single `.env` variable. This is not a wrapper around one API; it's an architectural commitment to vendor independence.

```python
# Every agent receives AIProvider via constructor — never imports providers
class ResearchAgent(BaseAgent):
    def __init__(self, provider: AIProvider, tm: ToolManager, task_mgr: TaskManager):
        self._provider = provider  # Provider-neutral
        self._tm = tm              # Tool registration
        self._task_mgr = task_mgr  # Task lifecycle + audit logs
```

#### 5. Complete Audit Trail
Every agent step is logged with structured data:
```
research_started → planning_started/completed → search_started/completed
→ extraction_started → intelligence_analysis_started/completed
→ synthesis_started → report_created → task_completed
```

This creates a debuggable, inspectable timeline for every prospect journey.

#### 6. Demo-Ready Workflow
One command seeds 5 complete companies with full lifecycle data (research reports, qualification scores, outreach drafts, inbound messages, pipeline status, agent logs) — and a 3-minute judge walkthrough guides the entire demo.

---

## Technical Architecture

### Core Abstraction Layer

```
┌────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
├────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐    │
│  │                  AIProvider (Protocol)              │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐  │    │
│  │  │Anthropic │ │  OpenAI  │ │FreeModel │ │ Local│  │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────┘  │    │
│  │        Resolved by ProviderManager at startup       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │              ToolManager (Plugin System)            │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │    │
│  │  │Web Search│ │Extractor │ │ Simulated Tools  │  │    │
│  │  │ (Tavily) │ │  (HTTP)  │ │  (Demo Fallback)  │  │    │
│  │  └──────────┘ └──────────┘ └──────────────────┘  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │              TaskManager (Lifecycle)                │    │
│  │  create → running → completed/failed + audit logs  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │              Agent Registry                         │    │
│  │  Research │ Qualification │ Outreach               │    │
│  │  Inbound │ Pipeline                               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │            Database Layer (PostgreSQL)              │    │
│  │  Companies │ Leads │ Reports │ Scores              │    │
│  │  Drafts │ Messages │ Pipeline │ Logs               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │        Mission Control UI (Jinja2 + Alpine.js)      │    │
│  │  Dashboard │ Leads │ Lead Detail │ Outreach        │    │
│  │  Pipeline │ Inbound │ Activity │ Demo              │    │
│  └────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

### Database Schema

```
companies ─── leads ─── conversations ─── inbound_messages
                │
                ├── research_tasks ─── research_reports
                │                              └── citations (JSONB)
                │                              └── intelligence_metadata (JSONB)
                │
                ├── qualification_results
                ├── outreach_drafts ─── outreach_history
                ├── pipeline_status
                └── agent_tasks ─── agent_logs
```

### Data Flow Pattern

```
Input (company/domain)
    │
    ├── Agent creates Task (via TaskManager)
    ├── Agent uses Tools (via ToolManager)
    ├── Agent calls AIProvider for synthesis
    ├── Agent persists structured output
    └── Agent marks task complete (with step logs)
```

Every agent follows the same pattern — `AIProvider + ToolManager + TaskManager` via constructor injection.

### Testing Strategy

| Layer | Count | Approach |
|-------|-------|----------|
| Unit tests | 204 | Mocked AIProvider, deterministic tools |
| Integration | 12 | Real FreeModelProvider (skipped without API key) |
| Demo script | 18 | File structure, output format, exit codes |
| Lint | ✅ Clean | ruff with 0 errors |

---

## Demo Walkthrough (3 Minutes)

### Minute 1: Landing → Dashboard → Lead Detail (0:00–1:00)

| Time | Action | Screen | Key Detail |
|------|--------|--------|------------|
| 0:00 | Open `/demo` | Demo intro page | Agent pipeline visualization |
| 0:05 | Click "Launch Demo Mission" | Brief loading state | Seeds 5 companies, auto-redirects |
| 0:15 | Dashboard loads | Mission Control | **5 total leads, 2 HOT** (SkyGrid 91, DroneFleet 85) |
| 0:25 | Pipeline snapshot | 8-stage Kanban | Leads mapped across stages |
| 0:35 | Click SkyGrid lead | Lead Detail | 🎯 Demo Account badge |
| 0:45 | Company Profile card | Profile data | Industry, 320 employees, San Francisco |
| 0:55 | Qualification card | Score gauge | 91/100 — ICP match 95, Buying signals 88 |

**🗣️ "The qualification card shows our hybrid scoring — deterministic rules for industry, size, and location combined with AI evaluation of buying signals and pain points. Every score is explainable with reasons and risks."**

### Minute 2: Outreach → Inbound (1:00–2:00)

| Time | Action | Screen | Key Detail |
|------|--------|--------|------------|
| 1:00 | Outreach Draft card | Lead Detail | Approved email to Sarah Chen |
| 1:10 | Strategy section | Detail | Email channel, "This week" urgency |
| 1:15 | Navigate to Outreach page | Draft queue | 3 drafts: approved, 2 pending |
| 1:20 | Click SkyGrid draft | Approval modal | Company intelligence brief |
| 1:25 | Inline editor + diff | Edit mode | BDR can edit, see word-level diff |
| 1:35 | Navigate to Inbound page | Message queue | Sarah Chen's reply |
| 1:45 | Message detail | Analysis | Intent: meeting_request (0.92), positive, high urgency |

**🗣️ "The human approval boundary means no message is ever auto-sent. Every draft requires BDR review, optional inline editing with diff visualization, and explicit approval. The inbound agent classified Sarah's message as a meeting request with 92% confidence."**

### Minute 3: Pipeline → Activity → Architecture (2:00–3:00)

| Time | Action | Screen | Key Detail |
|------|--------|--------|------------|
| 2:00 | Navigate to Pipeline | Kanban board | SkyGrid in "Meeting Scheduled" — 🎯 Demo indicator |
| 2:10 | Explore columns | All stages | 5 leads distributed across pipeline |
| 2:20 | Navigate to Activity | Timeline | Complete audit trail for all agents |
| 2:30 | Expand a task | Step-level logs | Every research step with structured data |
| 2:40 | Return to Dashboard | Summary | Pipeline snapshot, stats, activity feed |
| 2:50 | Architecture discussion | Code/docs | Provider-neutral, composable agents |

**🗣️ "The Activity page shows the complete audit trail for every agent execution — 13 step events for research, 9 for qualification, 9 for outreach, 8 for inbound, 6 for pipeline. Every decision is traceable."**

---

## Future Roadmap

| Feature | Description | Priority |
|---------|-------------|----------|
| **Email sending integration** | SendGrid/Resend adapter for approved outreach drafts | High |
| **Authentication** | JWT/session-based multi-user support with role-based access | High |
| **CRM integrations** | Salesforce, HubSpot sync for leads and pipeline stages | Medium |
| **Real-time research providers** | Google Custom Search, Bing as additional search backends | Medium |
| **Analytics dashboard** | Conversion rates, pipeline velocity, agent performance metrics | Medium |
| **Redis caching** | Cached search results and intelligence analysis for repeated queries | Low |
| **Continuous monitoring** | Periodic re-research for active leads with change detection | Low |

---

## Project Structure

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
    __init__.py        — Exports
    account_research.py — AccountResearchIntelligence (LLM analysis)
    outreach_brief.py  — CompanyIntelligenceBriefBuilder
  tools/
    base.py            — BaseTool ABC
    tool_manager.py    — ToolManager
    web_search.py      — WebSearchTool (Tavily + simulated)
    web_extractor.py   — WebContentExtractorTool (HTTP + simulated)
    simulated_web_search.py — Legacy simulated search
    simulated_content_extractor.py — Legacy simulated extractor
  db/
    base.py            — SQLAlchemy Base
    session.py         — Engine and session factory
    models.py          — All domain models (15 tables)
  api/
    router.py          — All REST endpoints (15+ endpoints)
  templates/           — 8 Jinja2 templates (Mission Control)
  static/
    css/app.css        — Tailwind + custom styles
    js/app.js          — Alpine.js + toast + animation helpers
tests/                 — 204 unit tests
scripts/
  seed_demo_data.py    — Demo data seeder
  demo.py              — One-command demo launcher
alembic/               — 4 database migrations
docs/                  — 10+ documentation files
```

---

## Quick Start

```bash
# One-command demo launcher
python scripts/demo.py

# Manual start
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000/demo
```

### Verification

```bash
# Run tests
pytest tests/ --tb=short -q    # 204 passed, 18 skipped

# Lint
ruff check . --no-cache        # All checks passed
```

---

## Submission Checklist

- [x] 5 specialized AI agents (Research, Qualification, Outreach, Inbound, Pipeline)
- [x] Account Intelligence Engine with real web search (Tavily) + LLM analysis
- [x] Human-in-the-loop approval for all outgoing communication
- [x] Inline editor with word-level diff visualization
- [x] Mission Control dashboard with 7 Jinja2 views
- [x] One-command demo launcher (`python scripts/demo.py`)
- [x] 3-minute judge walkthrough guide
- [x] Provider-neutral AI architecture
- [x] Complete audit trail with structured step logging
- [x] 204 passing tests, 0 lint errors
- [x] Seed script with 5 demo companies and full lifecycle data
- [x] Release tag: `hackathon-final-v1`
- [x] All documentation complete

# 🚀 ScoutOS — AI-Powered BDR Operating System

> **FlytBase Hackathon 2026** | Multi-agent prospect research, qualification, outreach, inbound handling, and pipeline intelligence — all under human control.

---

## What ScoutOS Does

ScoutOS transforms raw prospect data into pipeline opportunities through a coordinated pipeline of specialized AI agents. Each agent has distinct responsibilities, tools, and output structures:

```
Company/Domain
    │
    ▼
┌─────────────────────┐
│  Research Agent     │  → Company profile, tech stack, signals
│  (Web + LLM)        │  → Account Intelligence with citations
└────────┬────────────┘
         │
┌────────┴────────────┐
│  Qualification      │  → Hybrid scoring: rules + AI
│  Agent              │  → Priority: HOT / WARM / COLD
└────────┬────────────┘
         │
┌────────┴────────────┐
│  Outreach Agent     │  → Strategy → Personalization → Draft
│  (LLM + Templates)  │  → ❌ Never auto-sent
└────────┬────────────┘
         │  Human approval boundary
┌────────┴────────────┐
│  Inbound Agent      │  → Intent, sentiment, urgency
│  (LLM + Rules)      │  → Suggested reply
└────────┬────────────┘
         │
┌────────┴────────────┐
│  Pipeline Agent     │  → Stage health, stagnation risk
│  (Rules + LLM)      │  → Next best action
└─────────────────────┘
```

**Key differentiators:** Provider-neutral AI architecture, human-in-the-loop approval, complete audit trail, Account Intelligence Engine with real web search, and a polished Mission Control dashboard.

---

## One-Command Demo

```bash
# Requires: Python 3.14+, PostgreSQL, virtual environment
python scripts/demo.py

# Or manually:
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000/demo
```

The demo seeds 5 companies with complete lifecycle data (SkyGrid Inc., AeroVista, DroneFleet Logistics, AirMap Technologies, PrecisionAg Drones) and provides a 3-minute judge walkthrough from landing page through all 7 Mission Control views.

Manual inbound simulation at `/inbound/new` enables BDR teams to test lead qualification workflows without external email integrations. Submit a message to run Inbound → Qualification → Pipeline agents and open the analysis page at `/inbound/analysis/{task_id}`. Matching seeded accounts such as SkyGrid reuses existing demo intelligence.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │  AIProvider (Protocol)                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │  │
│  │  │Anthropic │ │  OpenAI  │ │FreeModel │ │ Local  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘  │  │
│  │  Resolved by ProviderManager — swap with .env config  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ToolManager (Plugin System)                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │  │
│  │  │Web Search│ │Extractor │ │ Simulated (Demo)   │  │  │
│  │  │ (Tavily) │ │  (HTTP)  │ │                    │  │  │
│  │  └──────────┘ └──────────┘ └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Agent Registry — 5 Specialized Agents               │  │
│  │  Research │ Qualification │ Outreach                 │  │
│  │  Inbound │ Pipeline                                  │  │
│  │  Every agent: AIProvider + ToolManager + TaskManager │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PostgreSQL (15 tables via SQLAlchemy)               │  │
│  │  Companies → Leads → Reports → Scores               │  │
│  │  Drafts → Messages → Pipeline → Audit Logs          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Mission Control UI (Jinja2 + Alpine.js + Tailwind)  │  │
│  │  8 views · Dark theme · Skeleton loading             │  │
│  │  Dashboard │ Leads │ Detail │ Outreach              │  │
│  │  Pipeline │ Inbound │ Activity │ Demo               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Core pattern:** `AIProvider + ToolManager + TaskManager` via constructor injection into every agent. This ensures provider neutrality, tool extensibility, and complete lifecycle management.

---

## Quick Reference

```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Activate environment
source .venv/bin/activate

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Seed demo data
python scripts/seed_demo_data.py

# Run tests
pytest tests/ --tb=short -q    # 204 passed, 18 skipped

# Lint
ruff check . --no-cache        # 0 errors

# Open demo
# http://localhost:8000/demo
```

---

## Screenshots

> *Screenshots to be added after hackathon judging.*

| View | Description |
|------|-------------|
| **Demo Page** | Launch point with agent pipeline visualization |
| **Dashboard** | Stats bar, pipeline snapshot, activity feed |
| **Lead Detail** | Company profile, qualification score gauge, outreach draft, pipeline position |
| **Outreach** | Draft queue with inline editor, diff view, approval modal |
| **Pipeline Kanban** | 8-stage horizontal-scrollable board with health indicators |
| **Inbound** | Message queue with AI analysis and suggested replies |
| **Activity** | Filterable audit timeline with step-level logs |

---

## Project Structure

```
app/                  → FastAPI backend application
  core/               → Contracts (AIProvider, BaseAgent), TaskManager, ToolManager
  providers/          → Anthropic, OpenAI, FreeModel, Local adapters
  agents/             → 5 specialized agents (research, qualification, outreach, inbound, pipeline)
  intelligence/       → Account Intelligence Engine, outreach brief builder
  tools/              → Web search, content extraction, simulated tools
  db/                 → SQLAlchemy models (15 tables), session, base
  api/                → REST endpoints (15+ endpoints)
  templates/          → 8 Jinja2 templates (Mission Control dashboard)
  static/             → CSS, JS (Tailwind + Alpine.js)
tests/                → 204 unit tests (providers, agents, tools, API, demo)
scripts/              → Demo launcher, seed script
alembic/              → 4 database migrations
docs/                 → Architecture, agents, demo, submission documentation
```

---

## Live Demo

> *Deployment URL placeholder — set after deploying to Railway.*

Once deployed:
```bash
# Health check
curl https://<your-railway-url>.up.railway.app/health

# Open demo
# https://<your-railway-url>.up.railway.app/demo
```

## Deployment

Deploy ScoutOS to Railway for a public demo:

```bash
# 1. Push to GitHub
# 2. Create Railway project from your GitHub repo
# 3. Add PostgreSQL plugin (DATABASE_URL auto-set)
# 4. Set env vars (AI_PROVIDER, ANTHROPIC_BASE_URL, etc.)
# 5. Railway auto-deploys — done!
```

**Local testing with Docker:**
```bash
docker compose up --build
# → http://localhost:8000
```

See [Deployment Guide](docs/DEPLOYMENT.md) for complete instructions.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Deployment Guide](docs/DEPLOYMENT.md) | Railway deployment instructions and environment setup |
| [Hackathon Submission](docs/HACKATHON_SUBMISSION.md) | Full submission package with architecture, demo walkthrough, differentiators |
| [Demo Scenario](docs/DEMO_SCENARIO.md) | 3-minute judge walkthrough with timed table and talking points |
| [Architecture](docs/ARCHITECTURE.md) | System design, layers, patterns |
| [Agent Design](docs/AGENT_DESIGN.md) | Agent interfaces, lifecycle, conventions |
| [Account Intelligence](docs/ACCOUNT_INTELLIGENCE.md) | Web search, extraction, LLM analysis pipeline |
| [Handbook](docs/CODEX_HANDOFF.md) | Continuation guide for future development |

---

## Release

- **Release Tag:** `hackathon-final-v1`
- **Commit:** `624f50b`
- **Tests:** 204 passed, 0 failed, 18 skipped
- **Lint:** Clean (ruff with 0 errors)
- **License:** MIT (see [LICENSE](LICENSE))

---

*Built for the FlytBase Hackathon 2026*

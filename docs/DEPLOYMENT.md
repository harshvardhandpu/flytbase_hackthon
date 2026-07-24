# ScoutOS — Deployment Guide

> Deploy ScoutOS to a public hosting platform for the FlytBase Hackathon 2026 demo.

---

## Recommended Platform: Railway

**Railway** is the recommended hosting platform for the ScoutOS hackathon demo because:

| Feature | Railway | Render (Free) | Fly.io |
|---------|---------|---------------|--------|
| PostgreSQL add-on | ✅ One-click | ✅ One-click | ❌ Manual setup |
| Auto-deploy from GitHub | ✅ Yes | ✅ Yes | ✅ Yes |
| Always-on (no sleep) | ✅ $5 credit covers 24/7 | ❌ Sleeps after 15min | ✅ Always-on |
| Python auto-detect | ✅ Nixpacks | ✅ Native | ❌ Requires Docker |
| Free tier | ✅ $5 credit, no CC needed | ✅ No CC needed | ❌ CC required |
| Setup complexity | ⭐ Simple | ⭐ Simple | ⭐⭐⭐ Complex |

**Verdict:** Railway provides the simplest path from repo to running demo with persistent PostgreSQL and no service sleep during judging.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   Railway Platform                          │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────┐  ┌────────────────────────┐ │
│  │   Web Service (Docker)   │  │  PostgreSQL Add-on     │ │
│  │   scoutos-app            │  │  scoutos-db            │ │
│  │                          │  │                        │ │
│  │   uvicorn app.main:app   │  │  Port: 5432            │ │
│  │   Port: $PORT            │  │  User: postgres        │ │
│  │   ─────────────────────  │  │  DB:   scoutos         │ │
│  │   /health  → 200         │  │                        │ │
│  │   /demo    → HTML        │  │  DATABASE_URL auto-set │ │
│  │   /api/v1/* → JSON       │  └────────────────────────┘ │
│  └──────────────────────────┘                             │
└────────────────────────────────────────────────────────────┘
```

### Startup Sequence

```
Container Start
    │
    ├── start.sh runs
    │   │
    │   ├── alembic upgrade head    (creates/migrates tables)
    │   ├── seed_demo_data.py       (seeds 5 demo companies)
    │   └── uvicorn app.main:app    (serves on $PORT)
    │
    └── FastAPI ready at http://<railway-url>
```

---

## Prerequisites

1. **GitHub account** — to fork/push the repository
2. **Railway account** — sign up at [railway.app](https://railway.app) (no credit card required)
3. **Tavily API key** (optional) — for real web search: [tavily.com](https://tavily.com)
4. **Anthropic/FreeModel credentials** (optional) — for AI-powered agents

---

## Deployment Steps

### Step 1: Push to GitHub

```bash
# Ensure your code is on GitHub
git remote add origin https://github.com/<your-username>/scoutos.git
git push -u origin main
```

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `scoutos` repository
4. Railway will auto-detect the `Dockerfile` and build the app

### Step 3: Add PostgreSQL Database

1. In the Railway dashboard, click **New** → **Database** → **Add PostgreSQL**
2. Railway will automatically create a PostgreSQL database
3. The `DATABASE_URL` environment variable is automatically injected into your web service

### Step 4: Configure Environment Variables

In the Railway dashboard, navigate to your web service → **Variables** tab and add:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `APP_ENV` | ✅ | Environment name | `production` |
| `AI_PROVIDER` | ✅ | AI provider to use | `freemodel` |
| `ANTHROPIC_BASE_URL` | ✅ (for AI) | FreeModel/Anthropic endpoint | `https://cc.freemodel.dev` |
| `ANTHROPIC_AUTH_TOKEN` | ✅ (for AI) | API auth token | `your-token-here` |
| `SEARCH_PROVIDER` | ❌ | Search provider | `simulated` (default) |
| `TAVILY_API_KEY` | ❌ | Tavily search API key | `tvly-your-key` |

> **Note:** `DATABASE_URL` is set automatically by the Railway PostgreSQL plugin.  
> **Note:** If `AI_PROVIDER` is not set, agents use `UnavailableProvider` and return fallback results.

### Step 5: Deploy

Railway auto-deploys when you push to the connected branch. To manually deploy:

```bash
# Install Railway CLI
curl -sSL https://railway.app/install.sh | sh

# Link to your project
railway login
railway link

# Deploy
railway up
```

### Step 6: Verify

Once deployed, Railway provides a URL like `https://scoutos-production.up.railway.app`.

```bash
# Health check
curl https://<your-url>.up.railway.app/health
# → {"status":"ok","environment":"production"}

# Demo page
# Open https://<your-url>.up.railway.app/demo
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | ✅ (auto) | `8000` | HTTP port (set by Railway) |
| `DATABASE_URL` | ✅ (auto) | — | PostgreSQL connection string (set by Railway plugin) |
| `APP_ENV` | ❌ | `development` | Environment name (`production`, `development`) |
| `AI_PROVIDER` | ❌ | `None` | AI backend: `anthropic`, `openai`, `freemodel`, `local` |
| `ANTHROPIC_BASE_URL` | ❌ | `None` | Anthropic-compatible API endpoint |
| `ANTHROPIC_AUTH_TOKEN` | ❌ | `None` | Anthropic API auth token |
| `ANTHROPIC_MODEL` | ❌ | `None` | Model name override |
| `OPENAI_API_KEY` | ❌ | `None` | OpenAI API key |
| `OPENAI_BASE_URL` | ❌ | `None` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | ❌ | `None` | OpenAI model name |
| `LOCAL_MODEL` | ❌ | `None` | Local model path |
| `SEARCH_PROVIDER` | ❌ | `simulated` | Search backend: `tavily` or `simulated` |
| `TAVILY_API_KEY` | ❌ | `None` | Tavily Search API key |
| `REDIS_URL` | ❌ | `None` | Redis connection string (future use) |

### AI Provider Resolution

```
AI_PROVIDER=freemodel              → Uses FreeModelProvider
AI_PROVIDER=anthropic              → Uses AnthropicProvider
AI_PROVIDER=openai                 → Uses OpenAIProvider
AI_PROVIDER=local                  → Uses LocalProvider (stub)
Not set + ANTHROPIC_BASE_URL set   → Auto-selects freemodel
Not set + OPENAI_API_KEY set       → Auto-selects openai
Not set + no credentials           → UnavailableProvider (fallback)
```

---

## Database Setup

Railway PostgreSQL is automatically configured. The `DATABASE_URL` environment variable is injected by the Railway plugin.

### Manual Migration (if needed)

```bash
# SSH into the running container or run locally with production DATABASE_URL
alembic upgrade head
python scripts/seed_demo_data.py
```

The `start.sh` script runs both commands automatically on container start, so no manual migration is needed.

### Alembic Configuration

Migrations are in `alembic/versions/`:
- `20260716_0001_initial_schema.py` — Core tables (companies, leads, etc.)
- `20260717_0001_phase3_qualification.py` — ICP configs, qualification results
- `20260718_0001_phase4_outreach.py` — Outreach drafts, history
- `20260720_0001_phase5_inbound_pipeline.py` — Inbound messages, pipeline stages
- `20260723_0001_account_intelligence.py` — Citations, intelligence metadata

---

## Demo Data

The `start.sh` script runs `python scripts/seed_demo_data.py` automatically on first start, creating:

- **5 companies** (SkyGrid Inc., AeroVista, DroneFleet Logistics, AirMap Technologies, PrecisionAg Drones)
- Full lifecycle data: research reports → qualification scores → outreach drafts → pipeline status
- 3 inbound messages from SkyGrid
- Default ICP config + 8 pipeline stages
- Agent audit logs

The seed script is **idempotent** — safe to run multiple times.

---

## Verifying the Deployment

### Quick Health Check

```bash
curl https://<your-url>.up.railway.app/health
# Expected: {"status":"ok","environment":"production"}
```

### Verify All Endpoints

```bash
# Demo page (HTML)
curl -s -o /dev/null -w '%{http_code}' https://<your-url>.up.railway.app/demo
# → 200

# Dashboard (HTML)
curl -s -o /dev/null -w '%{http_code}' https://<your-url>.up.railway.app/dashboard
# → 200

# API health
curl -s -o /dev/null -w '%{http_code}' https://<your-url>.up.railway.app/api/v1/pipeline/leads
# → 200

# Leads list
curl -s https://<your-url>.up.railway.app/api/v1/pipeline/leads | python3 -m json.tool | head -20
```

### Browser Verification

Open the following URLs in a browser and verify they render correctly:

| URL | Expected |
|-----|----------|
| `https://<your-url>.up.railway.app/demo` | Demo intro page with "Launch Demo Mission" |
| `https://<your-url>.up.railway.app/dashboard` | Mission Control dashboard with stats |
| `https://<your-url>.up.railway.app/leads` | Lead list with 5 companies |
| `https://<your-url>.up.railway.app/outreach` | Outreach drafts queue |
| `https://<your-url>.up.railway.app/inbound` | Inbound message queue |
| `https://<your-url>.up.railway.app/pipeline` | Pipeline Kanban board |
| `https://<your-url>.up.railway.app/activity` | Activity timeline |

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| App crashes on start | Missing `DATABASE_URL` | Ensure Railway PostgreSQL plugin is added |
| Migrations fail | Database not ready | Railway auto-creates DB, wait ~10s after adding plugin |
| "Lead not found" | Demo data not seeded | Check seed ran: `railway logs` should show seed output |
| Blank pages | Static files not loading | Verify `StaticFiles` mount works in Railway |
| API returns 500 | Missing AI credentials | Set `AI_PROVIDER=freemodel` or leave unset for fallback |
| Slow first load | Container cold start | Railway containers are always-on with paid credits |
| Console errors | Tailwind CDN warning | Non-blocking — Tailwind CDN dev warning is harmless |

### Viewing Logs

```bash
# Via Railway CLI
railway logs

# Via Railway Dashboard
# Navigate to your service → Logs tab
```

---

## Manual Non-Docker Deployment (Alternative)

If you prefer not to use Docker, Railway also supports Nixpacks (auto-detected Python):

```bash
# Railway auto-detects pyproject.toml
# Deploy without a Dockerfile by removing Dockerfile from the repo
# Railway will use Nixpacks to build and run:
#   uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

However, the `start.sh` script (migrations + seed) won't run automatically in Nixpacks mode. You would need to configure the start command manually in `railway.json`:

```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "./start.sh"
  }
}
```

---

## Local Testing with Docker Compose

```bash
# Build and start
docker compose up --build

# Access at http://localhost:8000

# Stop
docker compose down

# Stop and remove volumes
docker compose down -v
```

---

## Cost Estimate

Railway provides **$5 of free credits** per month, which comfortably covers:

| Service | Cost | Notes |
|---------|------|-------|
| Web service (1 vCPU, 512MB) | ~$0.0004/hr → ~$0.29/mo | Always-on during hackathon |
| PostgreSQL (512MB) | ~$2.00/mo | Included in free credits |
| **Total** | **~$2.29/mo** | Covered by $5 free credits |

No credit card required for the free tier.

---

## Post-Deployment

After deploying:

1. **Update `README.md`** with the live deployment URL
2. **Run the 3-minute demo walkthrough** from `docs/DEMO_SCENARIO.md`
3. **Verify all 8 views** load correctly on the public URL
4. **Test the `Launch Demo Mission` button** on the `/demo` page
5. **Verify SkyGrid's complete journey** (research → qualification → outreach → inbound → pipeline)

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [Hackathon Submission](HACKATHON_SUBMISSION.md) | Full submission package with differentiators |
| [Demo Scenario](DEMO_SCENARIO.md) | 3-minute judge walkthrough |
| [Architecture](ARCHITECTURE.md) | System design and patterns |
| [Agent Design](AGENT_DESIGN.md) | Agent lifecycle and conventions |
| [Account Intelligence](ACCOUNT_INTELLIGENCE.md) | Web search and analysis pipeline |

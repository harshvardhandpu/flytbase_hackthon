# Account Intelligence Engine

## Purpose

The Account Intelligence Engine upgrades ScoutOS research from simulated search
to real company intelligence. It provides:

- **Real web search** via Tavily API with automatic simulated fallback
- **Web content extraction** from URLs with HTML-to-text conversion
- **LLM-powered analysis** that transforms raw search results into structured,
  BDR-ready company intelligence
- **Citation tracking** for every source used in the analysis

This intelligence flows through the entire agent pipeline:

```
Company
  ↓
ResearchAgent
  ↓
  ├── WebSearchTool (Tavily or simulated)
  ├── WebContentExtractorTool (HTTP or simulated)
  └── AccountResearchIntelligence (AIProvider-based analysis)
  ↓
ResearchReport (with citations + intelligence_metadata)
  ↓
QualificationAgent
  ↓
Outreach Intelligence Brief
```

## Architecture

### Layer 1 — Tools (`app/tools/`)

```text
app/tools/
  base.py               ← BaseTool ABC
  tool_manager.py       ← ToolManager registry
  web_search.py         ← WebSearchTool (Tavily + simulated fallback)
  web_extractor.py      ← WebContentExtractorTool (HTTP + simulated fallback)
  simulated_web_search.py     ← Legacy simulated search (preserved for reference)
  simulated_content_extractor.py  ← Legacy simulated extractor (preserved for reference)
```

### Layer 2 — Intelligence (`app/intelligence/`)

```text
app/intelligence/
  account_research.py   ← AccountResearchIntelligence (LLM-based analysis)
  outreach_brief.py     ← CompanyIntelligenceBriefBuilder (deterministic brief)
```

### Layer 3 — Agents (`app/agents/`)

```text
app/agents/
  research.py           ← Upgraded ResearchAgent with Account Intelligence integration
```

## Key Components

### WebSearchTool

| Property | Value |
|----------|-------|
| `name` | `web_search` |
| Provider | Tavily Search API |
| Fallback | Simulated deterministic results |
| Auth | `TAVILY_API_KEY` env var |
| Config | `SEARCH_PROVIDER=tavily` or `simulated` (default) |

Executes search queries via Tavily's `/search` endpoint with `search_depth=advanced`.
When the API key is absent or the API call fails, returns deterministic mock results
matching known company patterns (FlytBase, drone inspection, etc.).

### WebContentExtractorTool

| Property | Value |
|----------|-------|
| `name` | `extract_web_content` |
| Method | HTTP GET + regex HTML stripping |
| Fallback | Simulated page content |
| Timeout | 10s per request |

Fetches a URL via `httpx`, strips HTML tags using regex while preserving
paragraph structure. Falls back to simulated content on network or parsing errors.

### AccountResearchIntelligence

| Property | Value |
|----------|-------|
| Input | Raw search results + extracted content + optional existing findings |
| Output | Structured intelligence dict |
| LLM | Via `AIProvider` (provider-neutral) |
| Fallback | Deterministic builder using existing findings |

Uses the AIProvider interface to generate structured analysis:

```json
{
  "company_situation": "2-3 sentence summary",
  "business_problems": ["Specific problem 1", "Specific problem 2"],
  "operational_risks": ["Risk of not solving problem 1"],
  "growth_signals": ["Hiring spree in X", "Opened new office in Y"],
  "buying_signals": ["Evaluating vendor solutions"],
  "technology_signals": ["Stack signal 1"],
  "flytbase_relevance": "High/Medium/Low — explanation",
  "industry_incidents": [{"title": "...", "summary": "...", "implication": "..."}],
  "recommended_sales_angle": "Specific angle for the BDR",
  "citations": [{"source": "...", "url": "...", "key_finding": "..."}]
}
```

### CompanyIntelligenceBriefBuilder

Updated to accept `account_intelligence` parameter. When provided, uses the
richer Account Intelligence fields directly. Falls back to deriving from raw
research signals when Account Intelligence is absent.

## Database Changes

One additive migration (`20260723_0001`) adds two columns to `research_reports`:

| Column | Type | Purpose |
|--------|------|---------|
| `citations` | JSONB | List of source citations with URLs and key findings |
| `intelligence_metadata` | JSONB | Analysis version, search/extraction counts |

No existing tables or columns were modified.

## Configuration

Add to `.env`:

```env
# Search Provider (tavily or simulated)
SEARCH_PROVIDER=tavily

# Tavily API Key (required when SEARCH_PROVIDER=tavily)
TAVILY_API_KEY=tvly-your-key-here
```

When `TAVILY_API_KEY` is absent or `SEARCH_PROVIDER=simulated`, all search
operations use the deterministic simulated fallback.

## Research Agent Step Events

The upgraded ResearchAgent emits these step events:

| Event | Phase | Description |
|-------|-------|-------------|
| `research_started` | Start | Research initiated for company |
| `planning_started` | Planning | LLM generating search queries |
| `planning_completed` | Planning | Search queries generated |
| `search_started` | Search | Web search executing for a query |
| `search_completed` | Search | Web search returned results |
| `extraction_started` | Extraction | Content extraction from sources |
| `tool_called` | Extraction | Individual URL extraction started |
| `tool_completed` | Extraction | Individual URL extraction done |
| `intelligence_analysis_started` | Intelligence | Account Intelligence analysis beginning |
| `intelligence_analysis_completed` | Intelligence | Account Intelligence analysis done |
| `synthesis_started` | Synthesis | LLM synthesising final report |
| `report_created` | Report | Research report persisted |
| `task_completed` | Complete | Agent task completed |

## Example Output

```json
{
  "report_id": "uuid",
  "findings": {
    "company_name": "SkyGrid Inc.",
    "domain": "skygrid.io",
    "industry": "Drone Services",
    "description": "2-3 sentence company overview",
    "business_signals": ["Hiring 20 engineers", "Series B funding"],
    "pain_points": ["Fleet coordination challenges"],
    "flytbase_relevance": "High — drone fleet management is core need",
    "company_situation": "SkyGrid Inc. shows hiring spree in engineering...",
    "growth_signals": ["Hiring 20 engineers", "New office in Austin"],
    "buying_signals": ["Evaluating drone management platforms"],
    "operational_risks": ["Coordination overhead as fleet scales"],
    "industry_incidents": [{"title": "...", "summary": "..."}]
  },
  "citations": [
    {"source": "https://skygrid.io/about", "url": "...", "key_finding": "..."}
  ],
  "intelligence_metadata": {
    "analysis_version": "1.0",
    "search_count": 4,
    "source_count": 8
  }
}
```

## Seed Data Demonstration

The `scripts/seed_demo_data.py` script demonstrates the Account Intelligence Engine
with pre-built intelligence data for all 5 demo companies. Each company includes:

### mock_search_results

Simulates `WebSearchTool` output — an array of search result objects, each with:
- `title` — Search result title
- `url` — Source URL
- `snippet` — Brief summary text

Example (SkyGrid Inc.):
```json
[
  {
    "title": "SkyGrid Series B — $40M for Drone Fleet Expansion",
    "url": "https://techcrunch.com/2026/01/skygrid-series-b",
    "snippet": "SkyGrid raised $40M in Series B funding..."
  },
  {
    "title": "SkyGrid Careers — Engineering Roles",
    "url": "https://skygrid.io/careers",
    "snippet": "SkyGrid is hiring robotics engineers..."
  }
]
```

### intelligence_data

Simulates `AccountResearchIntelligence` output — a structured dict with 10 fields:

| Field | Type | Example |
|-------|------|---------|
| `company_situation` | string | "SkyGrid is a well-funded ($40M Series B) drone fleet management company..." |
| `business_problems` | string[] | ["Manual flight planning consumes excessive engineering time..."] |
| `operational_risks` | string[] | ["EU expansion without centralised fleet ops could lead to fragmented telemetry..."] |
| `growth_signals` | string[] | ["hiring robotics engineers", "raised Series B ($40M)", "expanding to EU market"] |
| `buying_signals` | string[] | ["Evaluating fleet management platforms for multi-region operations"] |
| `technology_signals` | string[] | ["Python", "React", "AWS", "PostgreSQL", "Kubernetes"] |
| `flytbase_relevance` | string | "High — SkyGrid's fleet management complements FlytBase's drone-agnostic ground control..." |
| `industry_incidents` | object[] | [{"title": "...", "summary": "...", "implication": "..."}] |
| `recommended_sales_angle` | string | "Lead with operational visibility and control..." |
| `citations` | object[] | [{"source": "...", "url": "...", "key_finding": "..."}] |

### Data Flow in the Seed Script

```
COMPANIES list
 ├── profile_data (legacy — unchanged)
 ├── mock_search_results (new — simulates WebSearchTool)
 └── intelligence_data (new — simulates AccountResearchIntelligence)
         ↓
   ResearchTask.output_data.intelligence_metadata
   ResearchReport.citations + intelligence_metadata
         ↓
   CompanyIntelligenceBriefBuilder.build(account_intelligence=...)
         ↓
   Richer outreach briefs in CompanyIntelligenceBrief table
         ↓
   Outreach approval modal shows company-specific intelligence
```

Each company has **company-specific** intelligence:
- **SkyGrid Inc.** — EU expansion operations, Series B funding, drone fleet management
- **AeroVista** — Construction contract scaling, manual survey workflows
- **DroneFleet Logistics** — Multi-city fleet coordination, airspace deconfliction
- **AirMap Technologies** — EU regulatory pilot participation, strategic partnership angle
- **PrecisionAg Drones** — Indian agri-drone scaling, cost-sensitive remote operations

This creates a realistic demo where the outreach approval modal shows specific,
relevant intelligence for each company rather than generic fallback text.

## Future Extensions

- **Real-time web search**: Replace Tavily with a more sophisticated search API
  (Google Custom Search, Bing, etc.) by implementing the `BaseTool` interface.
- **Deeper content extraction**: Replace regex-based HTML stripping with
  a proper HTML-to-text library (trafilatura, readability, etc.).
- **Cached search results**: Add Redis-backed caching for repeated queries.
- **Multiple provider support**: Allow runtime selection between Tavily, Google,
  Bing, etc. via configuration.
- **Continuous monitoring**: Set up periodic re-research for active leads.

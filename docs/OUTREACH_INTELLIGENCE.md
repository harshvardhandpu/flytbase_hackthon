# Outreach Intelligence Brief

## Overview

The Outreach Intelligence Brief is a **deterministic, reusable intelligence layer** that provides BDRs with deeper company context before they approve an outreach message. It answers the question: *"Why should we contact this company now?"*

The brief is generated **before** human approval and displayed on the outreach approval screen alongside the email draft.

---

## Architecture

```
Research Report  ──┐
                    ├──> CompanyIntelligenceBriefBuilder ──> Brief stored as
Qualification ─────┘      CompanyIntelligenceBrief model     CompanyIntelligenceBrief
                                                                    │
                                                                    ▼
                                                         Displayed on Outreach
                                                         Approval Modal (UI)
```

### Key Design Decision

The intelligence builder is **deterministic** — it does NOT call an LLM. It transforms already-approved research and qualification data into a structured, reviewable brief. This ensures:
- **Reusability:** Any agent (Outreach, Inbound, Pipeline) can use the same builder
- **Stability:** The brief is identical given the same inputs
- **Explainability:** BDRs can trace every claim back to research data

---

## Directory Structure

```
app/intelligence/
  __init__.py              — Exports CompanyIntelligenceBriefBuilder
  outreach_brief.py        — Implementation
```

---

## Data Flow

### 1. Input (from ResearchAgent + QualificationAgent)

```python
{
  "company_name": "SkyGrid Inc.",
  "research": {
    "business_signals": [...],
    "pain_points": [...],
    "technology_signals": [...],
    "flytbase_relevance": "...",
    "industry": "Drone Technology"
  },
  "qualification": {
    "overall_score": 91,
    "priority": "HOT",
    "recommended_bdr_action": {
      "urgency": "Immediate",
      "suggested_sales_angle": "..."
    }
  }
}
```

### 2. Processing (CompanyIntelligenceBriefBuilder)

The builder:
1. Extracts business signals, pain points, and technology signals from research
2. Classifies signals into: growth, expansion, operational changes
3. Computes operational risks from detected problems
4. Selects relevant industry incidents from a knowledge base
5. Constructs the final structured brief

### 3. Output

```json
{
  "source": "simulated_structured_intelligence",
  "company_situation_summary": "SkyGrid Inc. shows Series B funding, hiring push, enterprise customer expansion. Its technology footprint includes AWS, Docker, Python, React.",
  "growth_signals": ["Series B funding ($30M)", "Hiring push in engineering"],
  "operational_changes": ["Expanding to 3 new markets"],
  "expansion_indicators": ["Enterprise customer base growing"],
  "technology_adoption_signals": ["AWS", "Docker", "Python", "React"],
  "detected_business_problems": [
    "Fleet scaling challenges at 50+ drones",
    "Operational complexity across regions"
  ],
  "operational_risks": [
    "If unresolved, fleet scaling challenges at 50+ drones can increase coordination overhead as operations grow."
  ],
  "flytbase_fit": {
    "summary": "Strong fit for drone fleet management needs...",
    "capabilities": [
      "Centralized fleet visibility and remote operations",
      "Automated mission planning and repeatable workflows",
      "API-based integration with operational systems"
    ]
  },
  "recommended_sales_angle": "Discuss how enterprise drone operators maintain visibility and control...",
  "relevant_incidents": [
    {
      "title": "Scaling operations can expose coordination gaps",
      "summary": "Demo industry context for Drone Technology: multi-site drone programs...",
      "urgency": "Use this as a discovery prompt..."
    }
  ]
}
```

### 4. Persistence (Database)

```python
class CompanyIntelligenceBrief(TimestampMixin, Base):
    __tablename__ = "company_intelligence_briefs"
    
    id: UUID (PK)
    outreach_draft_id: UUID (FK → outreach_drafts.id, unique)
    task_id: UUID (FK → agent_tasks.id)
    company_id: UUID (FK → companies.id)
    report_id: UUID? (FK → research_reports.id)
    qualification_id: UUID? (FK → qualification_results.id)
    brief_data: JSONB  # The full structured intelligence
    source: str  # "simulated_structured_intelligence"
```

### 5. Display (UI)

The intelligence brief is displayed in the **Outreach Approval Modal** on the `/outreach` page as a collapsible section with:

1. **Company Situation Summary** — Full-paragraph overview
2. **Growth Signals** | **Technology Signals** — Side-by-side grid
3. **Pain Analysis** — Detected problems with operational risks
4. **FlytBase Fit** — Value proposition + recommended sales angle
5. **Relevant Industry Context** — Incidents/case studies for urgency

---

## API Integration

The brief is generated and persisted automatically during the outreach creation flow:

1. `POST /api/v1/outreach` — Generates brief via `CompanyIntelligenceBriefBuilder`, persists as `CompanyIntelligenceBrief` record
2. `GET /api/v1/outreach/{task_id}` — Returns `company_intelligence` in response
3. UI displays brief in the approval modal before approve/reject buttons

---

## Database Migration

**Migration:** `alembic/versions/20260721_0001_outreach_intelligence.py`

Adds the `company_intelligence_briefs` table. No existing tables modified.

---

## Future Extensions

### 1. LLM-Enhanced Synthesis
The current builder is fully deterministic. A hybrid mode could:
- Use LLM to add industry-specific narratives
- Generate personalized "why now" reasoning using recent news

### 2. Real Incident Database
Replace simulated incidents with:
- Industry news API integration
- Case study database
- Competitor movement tracking

### 3. Reuse by Other Agents
The `CompanyIntelligenceBriefBuilder` can be reused by:
- **InboundAgent:** Add context to message triage
- **PipelineAgent:** Brief stage-transition decisions
- **QualificationAgent:** Deepen scoring explainability

### 4. Caching
The builder is stateless and deterministic — outputs can be cached by input hash for repeated lookups.

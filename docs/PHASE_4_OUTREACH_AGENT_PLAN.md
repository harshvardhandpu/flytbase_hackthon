# Phase 4 — Outreach Intelligence Agent Implementation Plan

## Overview

Build a BDR outreach agent that consumes `ResearchReport` (Phase 2) and `QualificationResult` (Phase 3) to generate personalized, editable email drafts with a human approval boundary. The agent crafts outreach strategy, personalization intelligence, and a complete email draft — but **never auto-sends**. Every draft requires explicit human approval before it can proceed to the send step (which is itself deferred to a later phase).

This follows the exact architectural pattern established in Phases 2 and 3:

```
OutreachAgent
  + AIProvider     (Protocol — never a concrete provider)
  + ToolManager    (for future enrichment tools, kept for consistency)
  + TaskManager    (lifecycle + audit logging)
```

---

## 1. Data Flow

```
ResearchReport (Phase 2 findings)
       │
       ▼
QualificationResult (Phase 3 scoring)
       │
       ▼
┌───────────────────────────────────────────────┐
│           Outreach Intelligence Agent          │
│                                               │
│  1. Load company profile + qualification       │
│  2. Generate outreach strategy                 │
│     - Recommended channel (email, linkedin...) │
│     - Urgency tier                             │
│     - Strategic reasoning                      │
│  3. Generate personalization intelligence      │
│     - Company hook (what makes them unique)    │
│     - Detected pain point (from research)      │
│     - FlytBase value proposition (tailored)    │
│  4. Generate editable outreach draft           │
│     - Subject line (testable)                  │
│     - Email body (with personalization)        │
│     - Follow-up suggestion                     │
│  5. Mark task as waiting_for_approval          │
│  6. Record draft in OutreachDraft table        │
└───────────────────────────────────────────────┘
       │
       ▼
┌───────────────────────────────────────────────┐
│           HUMAN APPROVAL BOUNDARY              │
│  POST /api/v1/outreach/{id}/approve           │
│  POST /api/v1/outreach/{id}/reject            │
│                                               │
│  Approved → OutreachHistory record created    │
│  Rejected → Draft marked with rejection notes │
└───────────────────────────────────────────────┘
       │
       ▼
  [Actual send deferred to future phase]
```

---

## 2. Input / Output Contract

### Input (consumed via task `input_data`)

The API layer resolves `ResearchReport` and `QualificationResult` from DB and passes them as structured context:

```json
{
  "company_name": "SkyGrid Inc.",
  "domain": "skygrid.io",
  "lead_id": "uuid | null",

  "research_findings": {
    "industry": "Drone Services",
    "employee_count": 180,
    "location": "Austin, TX",
    "description": "Drone fleet management for agriculture...",
    "business_signals": ["Series B funding", "Expanding to EU market"],
    "pain_points": ["Scaling inspection operations", "Manual pilot scheduling"],
    "technology_signals": ["DJI SDK integration", "Custom dashboard"],
    "flytbase_relevance": "High — operates drone fleets at scale",
    "sources": ["..."],
    "recommended_next_action": "Outreach with drone automation ROI"
  },

  "qualification": {
    "overall_score": 85,
    "icp_match_score": 90,
    "buying_signal_score": 82,
    "company_fit_score": 80,
    "priority": "HOT",
    "reasons": ["+ Industry matches ICP", "+ Series B funding signals growth"],
    "risks": ["- No direct purchase intent detected"],
    "reasoning": "Company operates drone fleets in agriculture...",
    "recommended_bdr_action": {
      "urgency": "Immediate",
      "suggested_sales_angle": "Lead with cost reduction and automation ROI"
    }
  }
}
```

### Output (from agent `output_data`)

```json
{
  "outreach_strategy": {
    "recommended_channel": "email",
    "urgency": "Immediate",
    "reasoning": "HOT lead with confirmed drone fleet operations and Series B funding indicates active budget."
  },

  "personalization": {
    "company_hook": "SkyGrid's expansion into EU agriculture aligns with FlytBase's multi-region deployment capabilities.",
    "detected_pain_point": "Manual pilot scheduling for 200+ daily inspections is a scaling bottleneck.",
    "flytbase_value_proposition": "FlytBase automates fleet orchestration, reducing pilot dependency by 60% and enabling remote 24/7 operations."
  },

  "email_draft": {
    "subject": "Re: Scaling SkyGrid's drone inspection operations across the EU",
    "body": "Hi [Contact Name],...",
    "follow_up_suggestion": "If no response in 5 days, follow up with a case study on similar agri-drone fleet that reduced costs by 40%."
  },

  "requires_human_approval": true,
  "providers_used": "anthropic"
}
```

---

## 3. DB Changes Required

Two new models, one migration (`alembic/versions/20260718_0001_phase4_outreach.py`).

### 3a. `OutreachDraft` Model

Stores the generated draft with its approval lifecycle. The `status` field tracks whether it has been human-reviewed.

```python
class OutreachDraft(TimestampMixin, Base):
    __tablename__ = "outreach_drafts"
    __table_args__ = (Index("ix_outreach_drafts_status", "status"),)

    id: Mapped[uuid.UUID] = UUID PK, default=uuid.uuid4
    task_id: Mapped[uuid.UUID] = FK → agent_tasks.id, nullable=False
    company_id: Mapped[uuid.UUID] = FK → companies.id, nullable=False
    lead_id: Mapped[uuid.UUID | None] = FK → leads.id
    report_id: Mapped[uuid.UUID | None] = FK → research_reports.id
    qualification_id: Mapped[uuid.UUID | None] = FK → qualification_results.id

    # ── Strategy ──────────────────────────────────────────────────
    strategy_channel: Mapped[str] = String(50), nullable=False       # "email" | "linkedin" | "phone"
    strategy_urgency: Mapped[str] = String(50), nullable=False      # "Immediate" | "This week" | "This month"
    strategy_reasoning: Mapped[str] = Text, default=""

    # ── Personalization ───────────────────────────────────────────
    company_hook: Mapped[str] = Text, default=""
    detected_pain_point: Mapped[str] = Text, default=""
    flytbase_value_proposition: Mapped[str] = Text, default=""

    # ── Draft ─────────────────────────────────────────────────────
    draft_subject: Mapped[str] = String(500), default=""
    draft_body: Mapped[str] = Text, default=""
    follow_up_suggestion: Mapped[str] = Text, default=""

    # ── Approval Lifecycle ────────────────────────────────────────
    status: Mapped[str] = String(50), default="pending_approval"
    # Statuses: pending_approval | approved | rejected | cancelled

    approval_notes: Mapped[str | None] = Text
    rejected_reason: Mapped[str | None] = Text
    approved_by: Mapped[str | None] = String(255)
    approved_at: Mapped[datetime | None] = DateTime(timezone=True)

    # ── Metadata ──────────────────────────────────────────────────
    provider: Mapped[str | None] = String(100)
    model: Mapped[str | None] = String(255)
```

**Why not `ApprovalStatus` as a separate model?** The `OutreachDraft.status` field is sufficient for the hackathon. A separate `ApprovalStatus` model (with `draft_id`, `action`, `actor`, `reason`, `timestamp` per row) is a clean extension for full audit trails later but adds complexity without immediate value. The `AgentLog` table already provides the audit trail for state transitions.

### 3b. `OutreachHistory` Model

Stores the immutable record of an approved/sent outreach. This is the permanent record that answer "what did we actually send to this lead?"

```python
class OutreachHistory(TimestampMixin, Base):
    __tablename__ = "outreach_history"
    __table_args__ = (Index("ix_outreach_history_lead_id", "lead_id"),)

    id: Mapped[uuid.UUID] = UUID PK, default=uuid.uuid4
    draft_id: Mapped[uuid.UUID] = FK → outreach_drafts.id, nullable=False
    company_id: Mapped[uuid.UUID] = FK → companies.id, nullable=False
    lead_id: Mapped[uuid.UUID | None] = FK → leads.id

    # Snapshot of what was sent (immutable copy)
    sent_subject: Mapped[str] = String(500), nullable=False
    sent_body: Mapped[str] = Text, nullable=False
    channel: Mapped[str] = String(50), nullable=False
    action: Mapped[str] = String(50), default="draft_approved"
    # Actions: draft_approved | sent | follow_up_sent | bounced

    # Approval metadata
    approved_by: Mapped[str | None] = String(255)
    approved_at: Mapped[datetime | None] = DateTime(timezone=True)

    # Response tracking
    response_received: Mapped[bool] = Boolean, default=False
    response_data: Mapped[dict[str, Any] | None] = JSONB
```

### 3c. Migration Details

- New file: `alembic/versions/20260718_0001_phase4_outreach.py`
- Creates `outreach_drafts` and `outreach_history` tables
- Foreign keys to `agent_tasks`, `companies`, `leads`, `research_reports`, `qualification_results`
- No existing models are modified

---

## 4. OutreachAgent Architecture

### Class Structure

```python
class OutreachAgent(BaseAgent):
    agent_type = "outreach"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
    ) -> None: ...

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        # 1. outreach_started
        # 2. Extract company profile, qualification data from input_data
        # 3. Generate outreach strategy (LLM)
        # 4. Generate personalization intelligence (LLM)
        # 5. Generate email draft (LLM)
        # 6. Assemble structured output
        # 7. Mark requires_human_approval=True
        # 8. outreach_completed
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Number of LLM calls** | 3 separate calls | Each step has a distinct purpose and prompt strategy. Combining them produces worse results. More importantly, separating them makes the audit log explainable — each step is independently logged and reviewable. |
| **Approval mechanism** | `requires_human_approval=True` on `AgentResult` | Follows the existing `AgentResult` contract from Phase 1. The `TaskManager.mark_waiting_for_approval()` already exists. |
| **DB data access** | Passed through `input_data` | Same pattern as Phase 3 — the API layer resolves reports and qualification results, passes them as dictionaries. No DB lookup tools needed. |
| **Channel selection** | LLM decides based on company signals | "email" is default, but the LLM can recommend "linkedin" if that fits the company's engagement patterns. |
| **Editable draft** | Stored in DB as text fields | The subject, body, and follow-up are stored as plain text so a future UI can render them in an editable form. |

### Step Logging Events

| Event | Level | When |
|-------|-------|------|
| `outreach_started` | info | Task begins |
| `context_loaded` | info | Company profile and qualification data loaded |
| `strategy_generation_started` | info | LLM generating outreach strategy |
| `strategy_generation_completed` | info | Strategy produced (channel, urgency, reasoning) |
| `personalization_started` | info | LLM generating personalization intelligence |
| `personalization_completed` | info | Personalization produced (hook, pain point, value prop) |
| `draft_generation_started` | info | LLM composing email draft |
| `draft_generation_completed` | info | Draft produced (subject, body, follow-up) |
| `outreach_completed` | info | Task completes with `requires_human_approval=True` |
| `outreach_strategy_failed` | error | Strategy generation fails |
| `outreach_personalization_failed` | error | Personalization generation fails |
| `outreach_draft_failed` | error | Draft generation fails |

### LLM Prompt Design

**Strategy Prompt** (system):
```
You are a BDR outreach strategist. Given a company's research profile and
qualification analysis, design the optimal outreach strategy.

Consider:
- The company's industry, signals, and pain points
- The qualification priority and urgency
- The sales angle recommended by the qualification analysis
- Which channel would be most effective for this type of lead

Return ONLY a JSON object with these exact keys:
{
  "recommended_channel": "email" | "linkedin" | "phone",
  "urgency": "Immediate" | "This week" | "This month",
  "reasoning": "2-3 sentence strategic rationale for the channel and urgency choice"
}
```

**Personalization Prompt** (system):
```
You are a BDR personalization specialist. Given a company's research profile
and qualification analysis, craft personalized messaging intelligence for
FlytBase outreach.

FlytBase is a drone fleet management platform that enables enterprises to
operate drone fleets remotely for automated missions.

Return ONLY a JSON object with these exact keys:
{
  "company_hook": "A 1-2 sentence hook that connects FlytBase to this specific company's mission, industry position, or recent achievement.",
  "detected_pain_point": "A 1-2 sentence description of the most relevant pain point from the research data that FlytBase can address.",
  "flytbase_value_proposition": "A 1-2 sentence tailored value proposition explaining how FlytBase solves the detected pain point, with specific capabilities."
}
```

**Draft Prompt** (system):
```
You are a senior BDR composing a personalized outreach email. Use the
outreach strategy and personalization intelligence provided.

Rules:
- Be specific and relevant to the recipient's company and role
- Reference the detected pain point early to show understanding
- Lead with value, not features
- Keep paragraphs short (2-3 sentences max)
- Include a clear, low-friction call to action
- Sound like a human, not a template
- Do NOT use placeholders like [Contact Name] — but indicate where
  personalization should happen (e.g., "Hi {{first_name}},")

Return ONLY a JSON object with these exact keys:
{
  "subject": "A compelling, personalized subject line under 60 characters",
  "body": "Full email body with paragraphs, personalized hook, value prop, and CTA",
  "follow_up_suggestion": "A 1-2 sentence suggestion for when and how to follow up if no response"
}
```

---

## 5. API Endpoints

### POST `/api/v1/outreach`

Creates an outreach task and generates a draft. Returns `status: "pending_approval"` — the draft is ready for human review, not auto-sent.

**Request:**
```json
{
  "company_name": "SkyGrid Inc.",
  "domain": "skygrid.io",
  "report_id": "uuid",
  "qualification_id": "uuid",
  "lead_id": "uuid | null"
}
```

At least one of `report_id` or `company_name` is required.

**Response (202 Accepted):**
```json
{
  "task_id": "uuid",
  "status": "pending_approval",
  "draft_id": "uuid"
}
```

### GET `/api/v1/outreach/{task_id}`

Retrieve the full outreach draft including strategy, personalization, and email content.

**Response:**
```json
{
  "task_id": "uuid",
  "status": "pending_approval",
  "agent_type": "outreach",
  "draft_id": "uuid",
  "company_name": "SkyGrid Inc.",
  "outreach_strategy": {
    "recommended_channel": "email",
    "urgency": "Immediate",
    "reasoning": "..."
  },
  "personalization": {
    "company_hook": "...",
    "detected_pain_point": "...",
    "flytbase_value_proposition": "..."
  },
  "email_draft": {
    "subject": "...",
    "body": "...",
    "follow_up_suggestion": "..."
  },
  "approval_summary": {
    "status": "pending_approval",
    "approved_by": null,
    "approved_at": null,
    "rejected_reason": null
  },
  "created_at": "...",
  "completed_at": "..."
}
```

### POST `/api/v1/outreach/{draft_id}/approve`

Human approval endpoint. Marks the draft as approved and creates an `OutreachHistory` record.

**Request:**
```json
{
  "approved_by": "harsh@flytbase.com",
  "approval_notes": "Looks good. Add mention of EU expansion."
}
```

**Response:**
```json
{
  "draft_id": "uuid",
  "status": "approved",
  "history_id": "uuid"
}
```

**Important:** This marks the draft as approved but does NOT send the message. A future phase handles actual sending.

### POST `/api/v1/outreach/{draft_id}/reject`

Human rejection endpoint. Records the rejection reason for the agent's feedback loop.

**Request:**
```json
{
  "rejected_reason": "Tone is too aggressive for this lead stage."
}
```

**Response:**
```json
{
  "draft_id": "uuid",
  "status": "rejected"
}
```

### GET `/api/v1/outreach/{draft_id}/history`

Retrieve the outreach history (approved/sent) for a specific draft.

**Response:**
```json
{
  "draft_id": "uuid",
  "history": [
    {
      "id": "uuid",
      "action": "draft_approved",
      "approved_by": "harsh@flytbase.com",
      "approved_at": "...",
      "sent_subject": "...",
      "sent_body": "...",
      "channel": "email",
      "response_received": false
    }
  ]
}
```

---

## 6. Implementation Order

| # | Component | Dependencies | Est. effort |
|---|-----------|-------------|-------------|
| 1 | DB models: `OutreachDraft` + `OutreachHistory` + migration | Phase 3 models | Small |
| 2 | `OutreachAgent` — full implementation with 3 LLM calls + step logging + `requires_human_approval` | #1, AIProvider, TaskManager | Medium |
| 3 | API endpoints: POST + GET + approve + reject + history | #2, router wiring | Medium |
| 4 | Update `registry.py` — promote `OutreachAgent` from skeleton to full implementation | #2 | Small |
| 5 | Tests: `OutreachAgent` (8+ tests — strategy, personalization, draft generation, step logging, edge cases) | #2 | Medium |
| 6 | Tests: API endpoints (6+ tests — validation, draft retrieval, approve/reject flow) | #3 | Medium |
| 7 | Run full test suite + lint | all | Small |
| 8 | Update docs: `FREEBUFF_CONTEXT.md`, `ROADMAP.md` | all | Small |

---

## 7. Testing Strategy

### OutreachAgent Tests (10+ tests)

| Test | What it verifies |
|------|------------------|
| `test_full_workflow_generates_draft` | Complete run returns strategy, personalization, and email draft |
| `test_strategy_generation` | Strategy output has valid channel, urgency, reasoning |
| `test_personalization_intelligence` | Personalization has hook, pain point, value prop |
| `test_draft_content` | Email draft has subject, body, follow-up suggestion |
| `test_requires_human_approval_flag` | `AgentResult.requires_human_approval` is `True` |
| `test_step_logging_events` | All 9+ expected log events are recorded |
| `test_handles_missing_context_gracefully` | No research/qualification data → graceful fallback |
| `test_handles_llm_strategy_failure` | LLM fails → fallback strategy returned |
| `test_handles_llm_draft_failure` | LLM fails → fallback draft returned |
| `test_empty_company_name` | No company data → minimal placeholder output |

### API Tests (8+ tests)

| Test | What it verifies |
|------|------------------|
| `test_create_outreach` | 202 response with task_id and draft_id |
| `test_create_outreach_missing_fields` | 422 when no identifiers provided |
| `test_get_outreach_task_status` | Returns full draft structure |
| `test_get_outreach_invalid_uuid` | 422 for bad task_id |
| `test_get_outreach_not_found` | 404 for non-existent task |
| `test_approve_draft` | Status changes to "approved", history created |
| `test_reject_draft` | Status changes to "rejected" with reason |
| `test_get_outreach_history` | Returns list of history records |

### DB Model Tests (2-3 tests)

| Test | What it verifies |
|------|------------------|
| `test_create_outreach_draft` | Draft persisted with all strategy/personalization/draft fields |
| `test_outreach_draft_status_defaults` | Default status is `pending_approval` |
| `test_create_outreach_history` | History record created with immutable snapshot |

---

## 8. What Future Agents Reuse

| Pattern | Reused by |
|---------|-----------|
| `OutreachAgent` constructor pattern (`AIProvider + ToolManager + TaskManager`) | Future agents (Inbound, Pipeline) — already established in Phases 2/3 |
| `requires_human_approval` + `mark_waiting_for_approval()` | Pipeline agent for status changes; Inbound agent for auto-replies |
| Approval/rejection API pattern | Pipeline approval flows, CRM data modification approvals |
| OutreachDraft → OutreachHistory archival pattern | Any agent with state transitions requiring permanent records |
| 3-prompt separation (strategy → personalization → draft) | Multi-step LLM workflows where each step needs independent explainability |
| LLM-driven channel selection | Future agents that need to recommend action channels |

---

## 9. Architectural Contract Checks

- ✅ **Provider-neutral**: `OutreachAgent` imports `AIProvider` (Protocol), never `AnthropicProvider` or `OpenAIProvider`
- ✅ **AIProvider + ToolManager + TaskManager** constructor injection — same as Phases 2 and 3
- ✅ **`requires_human_approval`** on `AgentResult` — already exists in the contract from Phase 1
- ✅ **No auto-send**: Agent returns a draft; the API stores it; a human must explicitly approve
- ✅ **No DB in agents**: All data passed through `input_data`; persistent storage handled by API layer
- ✅ **Step logging**: `append_log()` throughout the workflow for auditability
- ✅ **Historical records**: `OutreachHistory` stores immutable snapshots of approved drafts
- ✅ **New migration**: Does not modify Phase 1/2/3 models; creates new tables only
- ✅ **Thin API endpoints**: Parse HTTP, resolve DB records, call runtime, return results

---

## 10. Future-Proofing Notes

- **Actual sending**: The approval endpoint creates an `OutreachHistory` record but does not send. A future `POST /api/v1/outreach/{draft_id}/send` endpoint handles actual SMTP/API dispatch.
- **Approval workflow**: The current design uses a simple status field. For multi-person approval chains, add a separate `ApprovalStatus` model with per-row actor/action/timestamp records.
- **Template variables**: The email draft uses `{{first_name}}` placeholders. Future: Resolve these from `Contact` records before presenting to human reviewer.
- **A/B testing**: Future: Generate multiple drafts per lead and let the human pick.
- **Feedback loop**: Rejected drafts with reasons can be fed back into the LLM prompts to improve future drafts.
- **OutreachHistory responses**: The `response_received` and `response_data` fields are ready for when email tracking is added.
- **Tool enrichment**: The `ToolManager` is available for future enrichment tools (e.g., LinkedIn profile lookup, company news fetch) without changing the agent's constructor.

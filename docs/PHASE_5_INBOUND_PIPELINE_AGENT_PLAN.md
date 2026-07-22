# Phase 5 — Inbound & Pipeline Agent Implementation Plan

> **Status:** Plan ready for review  
> **Depends on:** Phase 4 (Outreach + approval endpoints)  
> **Est. effort:** 2-3 days of implementation

---

## Overview

Phase 5 builds two agents that close the BDR loop:

1. **InboundAgent** — Processes incoming messages (email, LinkedIn, form submissions), extracts intent/sentiment/urgency, identifies or creates leads/contacts, and classifies the message for the BDR workflow.

2. **PipelineAgent** — Evaluates a lead's position in the sales pipeline, aggregates history from all prior phases, detects stalled leads, and recommends the next best action.

Both agents follow the exact architectural pattern established in Phases 2-4:

```
Agent
  + AIProvider     (Protocol — never a concrete provider)
  + ToolManager    (for enrichment tools)
  + TaskManager    (lifecycle + audit logging)
```

---

## 1. Data Flow

### InboundAgent

```
Inbound Message (email, LinkedIn, form, webhook)
       │
       ▼
┌───────────────────────────────────────────────┐
│              Inbound Intelligence Agent        │
│                                               │
│  1. inbound_started                           │
│  2. Parse message content                     │
│     - intent_classification (question /       │
│       objection / purchase_intent /           │
│       support_request / meeting_request /     │
│       unsubscribe / other)                    │
│     - sentiment (positive / neutral /         │
│       negative)                               │
│     - urgency (high / medium / low)           │
│  3. Identify or create contact/lead           │
│     - Extract sender email, name, company     │
│     - Look up existing contact by email       │
│     - Create or update Lead record            │
│  4. Extract structured details                │
│     - Topics mentioned, role, budget hints    │
│     - Product interest, timeline              │
│  5. Classify and route                       │
│     - New inquiry → create lead               │
│     - Reply to outreach → update lead         │
│     - Objection → alert BDR                   │
│     - Meeting request → schedule              │
│  6. Generate suggested reply (if appropriate) │
│  7. Mark requires_human_approval for replies  │
│  8. inbound_completed                         │
└───────────────────────────────────────────────┘
       │
       ▼
┌───────────────────────────────────────────────┐
│           HUMAN APPROVAL BOUNDARY              │
│  Only if suggested reply generated             │
│  POST /api/v1/inbound/{id}/approve            │
│  POST /api/v1/inbound/{id}/reject             │
└───────────────────────────────────────────────┘
```

### PipelineAgent

```
Lead + All History (tasks, qualifications, outreach drafts, conversations)
       │
       ▼
┌───────────────────────────────────────────────┐
│           Pipeline Intelligence Agent          │
│                                               │
│  1. pipeline_evaluation_started               │
│  2. Aggregate lead data                       │
│     - Research findings                       │
│     - Qualification scores                    │
│     - Outreach drafts + approvals             │
│     - Inbound messages + responses            │
│     - Lead status history                     │
│  3. Evaluate pipeline position               │
│     - Current stage assessment                │
│     - Days in current stage                   │
│     - Stagnation detection                    │
│  4. Recommend next action                    │
│     - Suggested stage transition              │
│     - Action to take (email, call, nurture)   │
│     - Priority (urgent / soon / monitor)      │
│  5. pipeline_evaluation_completed             │
└───────────────────────────────────────────────┘
       │
       ▼
Recommended action (no auto-transition — BDR decides)
```

---

## 2. Input / Output Contracts

### 2a. InboundAgent

**Input** (via task `input_data`):

```json
{
  "message": {
    "from_email": "john@skygrid.io",
    "from_name": "John Smith",
    "subject": "Re: Your message about FlytBase",
    "body": "Hi, we're interested in learning more about your drone fleet management platform. We currently operate 50+ drones for infrastructure inspection and are looking to automate our workflows. Can we schedule a demo?",
    "channel": "email",
    "received_at": "2026-07-20T14:30:00Z"
  },
  "context": {
    "lead_id": "uuid | null",
    "contact_id": "uuid | null",
    "company_id": "uuid | null"
  }
}
```

**Output** (from agent `output_data`):

```json
{
  "message_id": "uuid",
  "analysis": {
    "intent": "meeting_request",
    "sentiment": "positive",
    "urgency": "high",
    "confidence": 0.92
  },
  "extracted_details": {
    "topics": ["drone fleet management", "automation", "infrastructure inspection"],
    "pain_points": ["manual workflows", "50+ drone operations"],
    "interest_signals": ["requested demo", "active budget signal"],
    "contact_role": "Operations Director",
    "company_size_hint": "Enterprise (50+ drones)"
  },
  "lead_action": {
    "action": "update_existing_lead",
    "lead_id": "uuid",
    "contact_id": "uuid | null",
    "status_update": "meeting_requested",
    "notes": "Prospect requested demo — high urgency, positive sentiment"
  },
  "suggested_reply": {
    "subject": "Re: Your message about FlytBase",
    "body": "Hi John,\n\nThanks for reaching out! We'd love to show you how FlytBase automates drone fleet operations...\n\nBest,\n[Your Name]",
    "follow_up_suggestion": "If no response in 3 days, send calendar link"
  },
  "requires_human_approval": true,
  "providers_used": "anthropic"
}
```

### 2b. PipelineAgent

**Input** (via task `input_data`):

```json
{
  "lead_id": "uuid",
  "company_id": "uuid",
  "lead_status": "outreach_completed",
  "days_in_stage": 14,
  "aggregated_data": {
    "research_task": {
      "status": "completed",
      "completed_at": "2026-07-18T10:00:00Z",
      "findings": { "...research findings..." }
    },
    "qualification_results": [
      {
        "overall_score": 85,
        "priority": "HOT",
        "created_at": "2026-07-18T10:30:00Z"
      }
    ],
    "outreach_drafts": [
      {
        "status": "approved",
        "created_at": "2026-07-19T09:00:00Z",
        "approved_at": "2026-07-19T15:00:00Z"
      }
    ],
    "inbound_messages": [...],
    "conversations": [
      {
        "direction": "inbound",
        "created_at": "2026-07-20T14:30:00Z"
      }
    ]
  }
}
```

**Output** (from agent `output_data`):

```json
{
  "lead_id": "uuid",
  "evaluation": {
    "current_stage": "outreach_completed",
    "stage_health": "stale",
    "days_in_stage": 14,
    "stagnation_risk": "moderate"
  },
  "lead_health": {
    "overall_health": "good",
    "engagement_level": "medium",
    "signal_decay": "low",
    "reengagement_needed": true
  },
  "recommended_action": {
    "type": "follow_up",
    "channel": "email",
    "stage_transition": "meeting_scheduled",
    "priority": "urgent",
    "action": "Send follow-up email with case study to re-engage",
    "reasoning": "Lead scored HOT, outreach approved 14 days ago, no response yet. Time to follow up with a relevant case study."
  },
  "providers_used": "anthropic"
}
```

---

## 3. DB Changes Required

One migration (`alembic/versions/20260720_0001_phase5_inbound_pipeline.py`) creating three new tables. No existing models are modified.

### 3a. `InboundMessage` Model

Stores the raw inbound message and its analysis. Reuses the existing `Conversation` table for bidirectional message history, but `InboundMessage` tracks the agent's analysis separately so it can be reviewed and approved.

```python
class InboundMessage(TimestampMixin, Base):
    """Inbound message with agent analysis.

    Stores the raw message, AI intent/sentiment/urgency analysis,
    extracted details, and any suggested reply. The message is also
    mirrored to the Conversation table for unified history.
    """

    __tablename__ = "inbound_messages"
    __table_args__ = (Index("ix_inbound_messages_lead_id", "lead_id"),)

    id: Mapped[uuid.UUID] = UUID PK, default=uuid.uuid4
    task_id: Mapped[uuid.UUID] = FK → agent_tasks.id, nullable=False
    conversation_id: Mapped[uuid.UUID | None] = FK → conversations.id

    # Who sent it
    from_email: Mapped[str] = String(320), nullable=False
    from_name: Mapped[str | None] = String(255)
    channel: Mapped[str] = String(50), nullable=False  # "email" | "linkedin" | "web_form"

    # Message content
    subject: Mapped[str | None] = String(500)
    body: Mapped[str] = Text, nullable=False
    received_at: Mapped[datetime] = DateTime(timezone=True), server_default=func.now()

    # Lead/contact links (resolved or created)
    lead_id: Mapped[uuid.UUID | None] = FK → leads.id
    contact_id: Mapped[uuid.UUID | None] = FK → contacts.id
    company_id: Mapped[uuid.UUID | None] = FK → companies.id

    # ── Agent Analysis ─────────────────────────────────────────────
    intent: Mapped[str | None] = String(50)
    # intents: question | objection | purchase_intent | support_request
    #          | meeting_request | unsubscribe | other

    sentiment: Mapped[str | None] = String(20)  # positive | neutral | negative
    urgency: Mapped[str | None] = String(20)     # high | medium | low
    confidence: Mapped[float | None] = Float     # 0.0 - 1.0

    extracted_details: Mapped[dict[str, Any] | None] = JSONB
    # { "topics": [...], "pain_points": [...], "interest_signals": [...],
    #   "contact_role": "...", "company_size_hint": "..." }

    # ── Suggested Action ───────────────────────────────────────────
    lead_action: Mapped[str | None] = String(50)
    # create_lead | update_lead | no_action

    suggested_status: Mapped[str | None] = String(50)
    # new | researching | qualified | meeting_requested | disqualified

    suggested_reply_subject: Mapped[str | None] = String(500)
    suggested_reply_body: Mapped[str | None] = Text
    follow_up_suggestion: Mapped[str | None] = Text

    # ── Approval Lifecycle ─────────────────────────────────────────
    status: Mapped[str] = String(50), default="pending_review"
    # pending_review | approved | rejected

    reviewed_by: Mapped[str | None] = String(255)
    reviewed_at: Mapped[datetime | None] = DateTime(timezone=True)
    review_notes: Mapped[str | None] = Text

    # ── Metadata ──────────────────────────────────────────────────
    provider: Mapped[str | None] = String(100)
    model: Mapped[str | None] = String(255)

    # Relationships
    task: Mapped[AgentTask] = relationship()
    conversation: Mapped[Conversation | None] = relationship()
```

**Why not just use Conversation?** The `Conversation` table stores raw message content. `InboundMessage` stores the **analysis** — intent, sentiment, urgency, extracted details, suggested reply, and approval lifecycle. The conversation record is created alongside the inbound message so the unified history (GET /outreach/{id}/history style) can show both outbound and inbound messages.

### 3b. `PipelineStage` Model

Configurable pipeline stages and their order. This is the master definition of the BDR pipeline.

```python
class PipelineStage(TimestampMixin, Base):
    """Configurable pipeline stage definition.

    Defines the stages a lead moves through in the BDR pipeline.
    The `order` field determines sequence. `is_active` allows
    stages to be disabled without removing historical data.
    """

    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = UUID PK, default=uuid.uuid4
    name: Mapped[str] = String(80), nullable=False     # e.g. "new", "researching"
    display_name: Mapped[str] = String(120), nullable=False  # e.g. "New Lead"
    description: Mapped[str | None] = Text
    order: Mapped[int] = Integer, nullable=False
    is_active: Mapped[bool] = Boolean, default=True
    color: Mapped[str | None] = String(20)  # UI hint: "blue", "green", "yellow"
```

### 3c. `PipelineStatus` Model

Per-lead pipeline status records, tracking every stage transition with reasoning.

```python
class PipelineStatus(TimestampMixin, Base):
    """Per-lead pipeline position and history.

    The `current` record holds the lead's present stage.
    Historical records provide the full pipeline journey.
    """

    __tablename__ = "pipeline_status"
    __table_args__ = (
        Index("ix_pipeline_status_lead_stage", "lead_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = UUID PK, default=uuid.uuid4
    lead_id: Mapped[uuid.UUID] = FK → leads.id, nullable=False
    task_id: Mapped[uuid.UUID | None] = FK → agent_tasks.id

    # ── Pipeline Position ─────────────────────────────────────────
    stage: Mapped[str] = String(80), nullable=False
    is_current: Mapped[bool] = Boolean, default=True
    entered_at: Mapped[datetime] = DateTime(timezone=True), server_default=func.now()

    # ── Intelligence ──────────────────────────────────────────────
    entered_by: Mapped[str] = String(50), default="agent"
    # "agent" | "human" | "system"

    reason: Mapped[str | None] = Text
    # e.g. "Lead scored HOT (85/100). Recommended: advance to outreach."
    # e.g. "Human approved outreach draft. Moving to meeting_scheduled."

    signal_summary: Mapped[str | None] = Text
    # e.g. "Engagement level: medium. Days in current stage: 14. Stagnation risk: moderate."

    recommended_next_action: Mapped[str | None] = Text
    # LLM-recommended next action text

    # ── Metadata ──────────────────────────────────────────────────
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    # Relationships
    lead: Mapped[Lead] = relationship()
    task: Mapped[AgentTask | None] = relationship()
```

### 3d. Migration Details

- New file: `alembic/versions/20260720_0001_phase5_inbound_pipeline.py`
- Creates `inbound_messages`, `pipeline_stages`, `pipeline_status` tables
- Foreign keys to `agent_tasks`, `conversations`, `leads`, `contacts`, `companies`
- Seeds default pipeline stages (new → researching → qualified → outreach → meeting_scheduled → negotiation → closed_won → closed_lost)
- Seeds the `Conversation` table's `direction` field usage (no schema change needed)
- No existing models are modified

---

## 4. Agent Architecture

### 4a. InboundAgent

**Class structure:**

```python
class InboundAgent(BaseAgent):
    agent_type = "inbound"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
    ) -> None: ...

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        # 1. inbound_started
        # 2. Parse message → intent, sentiment, urgency (LLM)
        # 3. Identify/merge lead and contact
        #    - Extract sender details from message
        #    - Check if existing conversation thread
        # 4. Extract structured details (LLM)
        #    - Topics, pain points, interest signals, role hints
        # 5. Classify and route
        #    - What action to take (create lead, update, no action)
        #    - Suggested lead status change
        # 6. Generate suggested reply (if inbound requires response)
        # 7. Mark requires_human_approval=True
        # 8. inbound_completed
```

**LLM calls:** Two calls minimum:

1. **Intent analysis call:**
   - System prompt: Classify inbound message intent, sentiment, urgency
   - User prompt: The message content
   - Output: `{ "intent": "...", "sentiment": "...", "urgency": "...", "confidence": 0.x, "extracted_details": {...} }`

2. **Lead action + reply call (if needed):**
   - System prompt: Determine what to do with this lead and draft a response
   - User prompt: The analysis + lead context
   - Output: `{ "lead_action": "...", "suggested_status": "...", "suggested_reply": {...}, "follow_up_suggestion": "..." }`

**Why two calls?** Separation of concerns. The first call is pure classification (no domain knowledge about leads needed). The second call uses the classification result plus lead context to decide what action to take. This matches the 3-stage approach from the OutreachAgent.

**Step logging events:**

| Event | Level | When |
|-------|-------|------|
| `inbound_started` | info | Task begins |
| `intent_analysis_started` | info | LLM analyzing intent/sentiment/urgency + extracting details |
| `intent_analysis_completed` | info | Intent classification and details received |
| `reply_generation_started` | info | LLM generating suggested reply and routing decision |
| `reply_generation_completed` | info | Reply draft created |
| `inbound_completed` | info | Task completes with requires_human_approval |
| `inbound_intent_failed` | error | Intent analysis LLM call fails |
| `inbound_reply_failed` | error | Reply generation LLM call fails |

**Note:** Lead identification and routing happen in the API layer, not the agent — same pattern as Phases 3-4 where the API resolves reports/ICP configs before creating the task. The agent receives the resolved context via `input_data`.

**Key design decision — When `requires_human_approval` is set:**

- `requires_human_approval=True` if a suggested reply was generated
- `requires_human_approval=False` if the message is purely informational (e.g., auto-reply, unsubscribe, spam) and no reply is needed

This matches the OutreachAgent pattern where not everything needs approval, but anything that sends a message does.

**Lead.status update timing:**
The API layer applies the agent's suggested status update to `Lead.status` as follows:
- If `requires_human_approval=False` and `suggested_status` is set → update immediately after agent completes.
- If `requires_human_approval=True` → wait until the approve/reject endpoint is called before updating.

### 4b. PipelineAgent

**Class structure:**

```python
class PipelineAgent(BaseAgent):
    agent_type = "pipeline"

    def __init__(
        self,
        ai_provider: AIProvider,
        tool_manager: ToolManager,
        task_manager: TaskManager,
    ) -> None: ...

    async def run(self, context: AgentContext, task: AgentTaskInput) -> AgentResult:
        # 1. pipeline_evaluation_started
        # 2. Aggregate lead data from input_data
        # 3. Evaluate pipeline position and health (LLM + rules)
        # 4. Detect stagnation
        # 5. Recommend next action
        # 6. pipeline_evaluation_completed
        # 7. NO human approval needed (just recommendations)
```

**LLM calls:** One call (deterministic rules handle stage detection, LLM handles recommendation quality):

1. **Pipeline evaluation call:**
   - System prompt: Evaluate lead pipeline position and recommend next action
   - User prompt: Aggregated lead data + current stage
   - Output: `{ "stage_health": "...", "stagnation_risk": "...", "overall_health": "...", "recommended_action": {...} }`

**Deterministic rules (pre-LLM):**

```python
def _compute_stage_health(current_stage: str, days_in_stage: int) -> str:
    # Rules-based stage health assessment
    stage_timeouts = {
        "new": 7,            # If new > 7 days → stale
        "researching": 5,    # If researching > 5 days → stale
        "qualified": 3,      # If qualified > 3 days → stale
        "outreach": 7,       # If outreach sent > 7 days without response → stale
        "meeting_scheduled": 14,  # If meeting > 14 days ago → stale
        "negotiation": 30,   # If negotiation > 30 days → stale
    }
    timeout = stage_timeouts.get(current_stage, 7)
    if days_in_stage > timeout * 2:
        return "critical"
    if days_in_stage > timeout:
        return "stale"
    return "healthy"

def _compute_stagnation_risk(days_in_stage: int, engagement_count: int) -> str:
    if days_in_stage > 21 and engagement_count == 0:
        return "high"
    if days_in_stage > 14:
        return "moderate"
    return "low"
```

**Step logging events:**

| Event | Level | When |
|-------|-------|------|
| `pipeline_evaluation_started` | info | Task begins |
| `lead_data_aggregated` | info | Lead data loaded from input |
| `deterministic_analysis_completed` | debug | Stage health + stagnation computed |
| `llm_evaluation_started` | info | LLM evaluating pipeline position |
| `llm_evaluation_completed` | info | LLM returns recommendations |
| `pipeline_evaluation_completed` | info | Task completes |

**`requires_human_approval`: Always `False`.** The PipelineAgent only recommends — it never takes action. The BDR decides whether to follow the recommendation.

---

## 5. API Endpoints

### 5a. Inbound Endpoints

#### POST `/api/v1/inbound`

Process an inbound message. Returns analysis with suggested reply if appropriate.

**Request:**
```json
{
  "from_email": "john@skygrid.io",
  "from_name": "John Smith",
  "subject": "Re: FlytBase demo request",
  "body": "Hi, we'd like to schedule a demo...",
  "channel": "email",
  "received_at": "2026-07-20T14:30:00Z",
  "lead_id": "uuid | null",
  "contact_id": "uuid | null"
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "uuid",
  "message_id": "uuid",
  "status": "pending_review",
  "intent": "meeting_request",
  "sentiment": "positive",
  "urgency": "high",
  "lead_action": "update_existing_lead",
  "requires_human_approval": true,
  "suggested_reply_preview": "Hi John,\n\nThanks for reaching out!..."
}
```

#### GET `/api/v1/inbound/{task_id}`

Retrieve the full inbound analysis.

**Response:**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "agent_type": "inbound",
  "message": {
    "from_email": "john@skygrid.io",
    "from_name": "John Smith",
    "subject": "...",
    "body": "...",
    "channel": "email"
  },
  "analysis": {
    "intent": "meeting_request",
    "sentiment": "positive",
    "urgency": "high",
    "confidence": 0.92,
    "extracted_details": { ... }
  },
  "lead_action": {
    "action": "update_existing_lead",
    "lead_id": "uuid",
    "status_update": "meeting_requested"
  },
  "suggested_reply": {
    "subject": "...",
    "body": "..."
  },
  "approval_summary": {
    "status": "pending_review"
  }
}
```

#### POST `/api/v1/inbound/{message_id}/approve`

Approve the suggested reply for an inbound message.

**Request:**
```json
{
  "approved_by": "bdr@flytbase.com",
  "approval_notes": "Good response. Add pricing link."
}
```

**Response:**
```json
{
  "message_id": "uuid",
  "status": "approved"
}
```

#### POST `/api/v1/inbound/{message_id}/reject`

Reject the suggested reply.

**Request:**
```json
{
  "rejected_reason": "Response is too generic for this lead"
}
```

**Response:**
```json
{
  "message_id": "uuid",
  "status": "rejected"
}
```

### 5b. Pipeline Endpoints

#### POST `/api/v1/pipeline/evaluate`

Evaluate a lead's pipeline position.

**Request:**
```json
{
  "lead_id": "uuid"
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "uuid",
  "lead_id": "uuid",
  "status": "completed",
  "current_stage": "outreach",
  "stage_health": "stale",
  "stagnation_risk": "moderate",
  "recommended_action": {
    "type": "follow_up",
    "channel": "email",
    "stage_transition": "meeting_scheduled",
    "priority": "urgent",
    "action": "Send follow-up with case study"
  }
}
```

#### GET `/api/v1/pipeline/{task_id}`

Retrieve pipeline evaluation result.

#### POST `/api/v1/pipeline/{lead_id}/advance`

Manually advance a lead to the next stage (human override).

**Request:**
```json
{
  "new_stage": "meeting_scheduled",
  "reason": "Prospect confirmed demo slot",
  "advanced_by": "bdr@flytbase.com"
}
```

**Response:**
```json
{
  "lead_id": "uuid",
  "new_stage": "meeting_scheduled",
  "previous_stage": "outreach",
  "status_id": "uuid"
}
```

#### GET `/api/v1/pipeline/leads`

List leads with their current pipeline status.

**Query parameters:**
- `stage` (optional) — filter by pipeline stage
- `status` (optional) — filter by lead status
- `health` (optional) — filter by stage health (healthy | stale | critical)
- `limit` (default 50)

**Response:**
```json
{
  "leads": [
    {
      "lead_id": "uuid",
      "company_name": "SkyGrid Inc.",
      "current_stage": "outreach",
      "stage_health": "stale",
      "days_in_stage": 14,
      "overall_score": 85,
      "priority": "HOT",
      "next_action": "Send follow-up email"
    }
  ],
  "total": 1,
  "filtered_by": { "health": "stale" }
}
```

---

## 6. Tool Design

### InboundAgent Tools

The InboundAgent works primarily on the message data passed through `input_data`. No DB lookup tools are needed — the API layer resolves existing leads/contacts and passes them as context.

However, one enrichment tool is useful:

**`identify_contact` (optional enrichment tool):**
```python
class IdentifyContactTool(BaseTool):
    name = "identify_contact"
    description = "Look up or create a lead/contact by email address"

    async def execute(self, payload) -> ToolResult:
        # Takes: { "email": "...", "name": "...", "company": "..." }
        # Returns: { "lead_id": "uuid | null", "contact_id": "uuid | null",
        #            "company_id": "uuid | null", "is_new": bool }
```

**Decision: Skip the tool for Phase 5.** The API layer can handle lead identification before creating the task, passing the resolved context through `input_data`. This keeps the agent simpler and follows the Phase 3/4 pattern of passing context through input_data.

### PipelineAgent Tools

**Decision: No new tools needed.** All lead data is aggregated by the API layer and passed through `input_data`. The PipelineAgent operates on structured data only.

---

## 7. Implementation Order

| # | Component | Dependencies | Est. effort |
|---|-----------|-------------|-------------|
| 1 | DB models: `InboundMessage` + `PipelineStage` + `PipelineStatus` + migration | Phase 4 models | Small |
| 2 | `InboundAgent` — message parsing, intent analysis, lead identification, reply generation, step logging | #1, AIProvider, TaskManager | Medium |
| 3 | `PipelineAgent` — aggregation, stage health rules, stagnation detection, LLM recommendation, step logging | #1, AIProvider, TaskManager | Medium |
| 4 | API endpoints — inbound (POST, GET, approve, reject) | #2 | Medium |
| 5 | API endpoints — pipeline (POST evaluate, GET, advance, list) | #3 | Medium |
| 6 | Update `registry.py` — promote both agents from skeletons to full implementations | #2, #3 | Small |
| 7 | Tests: `InboundAgent` (10+ tests) | #2 | Medium |
| 8 | Tests: `PipelineAgent` (8+ tests) | #3 | Medium |
| 9 | Tests: API endpoints (12+ tests) | #4, #5 | Medium |
| 10 | Full suite + lint + code review | all | Small |
| 11 | Update docs: `FREEBUFF_CONTEXT.md`, `ROADMAP.md` | all | Small |

---

## 8. Testing Strategy

### InboundAgent Tests (10+ tests)

| Test | What it verifies |
|------|------------------|
| `test_full_workflow_new_inquiry` | Complete run: classifies intent, identifies lead, generates reply |
| `test_intent_classification_meeting_request` | "Can we schedule a demo?" → intent = "meeting_request" |
| `test_intent_classification_objection` | "Your pricing is too high" → intent = "objection" |
| `test_sentiment_detection_positive` | Positive language → sentiment = "positive" |
| `test_sentiment_detection_negative` | Negative language → sentiment = "negative" |
| `test_urgency_detection_high` | Urgent language → urgency = "high" |
| `test_handles_existing_lead` | lead_id provided → updates existing, doesn't create new |
| `test_handles_no_reply_needed` | Informational message → requires_human_approval = False |
| `test_requires_approval_for_reply` | Reply generated → requires_human_approval = True |
| `test_step_logging_events` | All expected log events recorded |
| `test_handles_empty_message_gracefully` | Empty body → graceful fallback |

### PipelineAgent Tests (8+ tests)

| Test | What it verifies |
|------|------------------|
| `test_full_workflow_evaluation` | Complete run produces stage health, stagnation risk, recommendation |
| `test_healthy_stage_detection` | Lead new for 2 days → stage_health = "healthy" |
| `test_stale_stage_detection` | Lead in outreach for 14 days → stage_health = "stale" |
| `test_critical_stage_detection` | Lead in outreach for 30 days with no engagement → "critical" |
| `test_stagnation_risk_high` | No engagement for 21+ days → stagnation_risk = "high" |
| `test_llm_recommendation_fallback` | LLM fails → deterministic recommendation |
| `test_handles_no_history_lead` | New lead with no history → sensible default assessment |
| `test_step_logging_events` | All expected log events recorded |

### API Tests (12+ tests)

| Test | What it verifies |
|------|------------------|
| `test_inbound_process_message` | 202 response with analysis and message_id |
| `test_inbound_missing_fields` | 422 when no message body provided |
| `test_inbound_get_analysis` | Returns full analysis with intent, sentiment, urgency |
| `test_inbound_approve_reply` | Status changes to "approved" |
| `test_inbound_reject_reply` | Status changes to "rejected" with reason |
| `test_pipeline_evaluate_lead` | 202 response with evaluation |
| `test_pipeline_evaluate_missing_lead` | 422 when no lead_id provided |
| `test_pipeline_get_evaluation` | Returns full evaluation result |
| `test_pipeline_advance_lead` | Lead stage updated, history record created |
| `test_pipeline_advance_invalid_stage` | 422 for invalid stage name |
| `test_pipeline_list_leads` | Returns paginated lead list with pipeline status |
| `test_pipeline_list_leads_filtered` | Filtering by stage and health works |

---

## 9. What Future Phases Reuse

| Pattern | Reused by |
|---------|-----------|
| `InboundAgent`'s intent classification | Chat/email integration adapters (send/receive via API) |
| `PipelineAgent`'s aggregation + recommendation | Dashboard views, lead scoring refresh cron |
| `InboundMessage` model + approval | Auto-reply engine, chatbot orchestration |
| `PipelineStatus` history tracking | Pipeline analytics, conversion rate reporting |
| Manual advance endpoint (pipeline override) | CRM integration (HubSpot, Salesforce sync) |
| Stage health + stagnation rules | Alerting/notification system for stale leads |

---

## 10. Architectural Contract Checks

- ✅ **Provider-neutral**: Both agents import `AIProvider` (Protocol), never concrete providers
- ✅ **AIProvider + ToolManager + TaskManager** constructor injection — same as Phases 2-4
- ✅ **`requires_human_approval`** on `AgentResult` — InboundAgent uses it conditionally, PipelineAgent sets it to `False`
- ✅ **No auto-reply**: InboundAgent returns a suggested reply; a human must explicitly approve
- ✅ **No auto-transition**: PipelineAgent only recommends; the advance endpoint requires human action
- ✅ **No DB in agents**: All data passed through `input_data`; API layer handles persistence
- ✅ **Step logging**: `append_log()` throughout for auditability
- ✅ **Historical records**: `PipelineStatus` tracks every transition; `InboundMessage` stores analysis
- ✅ **New migration**: Does not modify Phase 1-4 models; creates new tables only
- ✅ **Thin API endpoints**: Parse HTTP, resolve DB records, call runtime, return results
- ✅ **Simulated default**: Both agents use `AIProvider.generate()` for LLM calls; no real API calls in agent code

---

## 11. Risk and Mitigations

| Risk | Mitigation |
|------|-----------|
| InboundAgent misclassifies intent | The `confidence` field lets humans assess reliability. Low-confidence messages can be flagged for manual review. |
| PipelineAgent recommends wrong action | All recommendations are advisory only. The `POST /api/v1/pipeline/{lead_id}/advance` endpoint requires explicit human input. |
| Inbound message contains PII or sensitive data | The `InboundMessage` model stores the raw body; a future sanitization step can strip PII before analysis. |
| Lead identification fails (email not found, ambiguous) | The intent analysis still works without a lead match. The message is stored with `lead_action: "create_lead"` for manual review. |
| Too many endpoints for hackathon timeline | Prioritize: InboundAgent + PipelineAgent core logic first, then essential API endpoints. Advanced features (pipeline list filtering, batch operations) are stretch goals. |

---

## 12. Future-Proofing Notes

- **Real email integration**: The `POST /api/v1/inbound` endpoint is designed to be called by an email webhook (SendGrid, Mailgun, etc.). No adapter changes needed in the agent.
- **Auto-reply engine**: Once the approval workflow stabilizes, add a `POST /api/v1/inbound/{message_id}/send` endpoint that actually dispatches the approved reply.
- **Pipeline automation**: The `PipelineAgent` recommendations could feed into a nightly batch job that auto-advances or alerts on stale leads.
- **Dashboard integration**: The `GET /api/v1/pipeline/leads` endpoint is designed to directly power a pipeline Kanban board or list view.
- **Stage weights**: The deterministic rules for stage health can be stored in a config (JSONB on `PipelineStage`) instead of hardcoded.
- **Lead scoring refresh**: The PipelineAgent could trigger a re-qualification if the lead has been in a stage too long, creating a feedback loop back to Phase 3.

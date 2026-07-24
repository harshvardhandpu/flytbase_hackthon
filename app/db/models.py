from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), unique=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    contacts: Mapped[list[Contact]] = relationship(back_populates="company")
    leads: Mapped[list[Lead]] = relationship(back_populates="company")
    research_reports: Mapped[list[ResearchReport]] = relationship(back_populates="company")


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    title: Mapped[str | None] = mapped_column(String(255))
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    company: Mapped[Company] = relationship(back_populates="contacts")
    leads: Mapped[list[Lead]] = relationship(back_populates="contact")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="contact")


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    score_reasoning: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    company: Mapped[Company] = relationship(back_populates="leads")
    contact: Mapped[Contact | None] = relationship(back_populates="leads")
    tasks: Mapped[list[AgentTask]] = relationship(back_populates="lead")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="lead")


class AgentTask(TimestampMixin, Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (Index("ix_agent_tasks_status_type", "status", "agent_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    lead: Mapped[Lead | None] = relationship(back_populates="tasks")
    logs: Mapped[list[AgentLog]] = relationship(back_populates="task", cascade="all, delete-orphan")
    reports: Mapped[list[ResearchReport]] = relationship(back_populates="task")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[AgentTask] = relationship(back_populates="logs")


class ResearchReport(TimestampMixin, Base):
    __tablename__ = "research_reports"
    __table_args__ = (Index("ix_research_reports_company_id", "company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_tasks.id"))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    intelligence_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))

    company: Mapped[Company] = relationship(back_populates="research_reports")
    task: Mapped[AgentTask | None] = relationship(back_populates="reports")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_lead_id", "lead_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    lead: Mapped[Lead | None] = relationship(back_populates="conversations")
    contact: Mapped[Contact | None] = relationship(back_populates="conversations")


class IcpConfig(TimestampMixin, Base):
    """Ideal Customer Profile configuration.

    Stores ICP rules used by QualificationAgent for lead scoring.
    Multiple configs can coexist; is_active selects the default.
    """

    __tablename__ = "icp_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industries: Mapped[list[str]] = mapped_column(JSONB, default=list)
    min_employees: Mapped[int | None] = mapped_column(Integer)
    max_employees: Mapped[int | None] = mapped_column(Integer)
    locations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    technology_signals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    qualification_results: Mapped[list[QualificationResult]] = relationship(
        back_populates="icp_config"
    )


class QualificationResult(TimestampMixin, Base):
    """Audit record of a qualification run.

    Stores the complete scoring output — component scores, priority,
    explainable reasoning, and recommended BDR action.
    """

    __tablename__ = "qualification_results"
    __table_args__ = (Index("ix_qualification_task_id", "task_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_reports.id"))
    icp_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("icp_configs.id"))

    # ── Component scores (0-100 each) ────────────────────────────────
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    icp_match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    buying_signal_score: Mapped[int] = mapped_column(Integer, nullable=False)
    company_fit_score: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Priority classification ──────────────────────────────────────
    priority: Mapped[str] = mapped_column(String(10), nullable=False)  # HOT | WARM | COLD

    # ── Explainability ───────────────────────────────────────────────
    reasoning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    risks: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # ── BDR action recommendation (input for Outreach Agent) ─────────
    recommended_urgency: Mapped[str | None] = mapped_column(String(50))
    recommended_sales_angle: Mapped[str | None] = mapped_column(Text)

    # ── Snapshot of ICP config used (in case config changes later) ───
    icp_inline_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))

    # ── Relationships ────────────────────────────────────────────────
    task: Mapped[AgentTask] = relationship()
    company: Mapped[Company] = relationship()
    icp_config: Mapped[IcpConfig | None] = relationship(back_populates="qualification_results")


class OutreachDraft(TimestampMixin, Base):
    """Generated outreach draft with human approval lifecycle.

    Stores the full strategy, personalization intelligence, email draft,
    and approval status. No message is auto-sent; a human must approve
    before the draft transitions to approved status.
    """

    __tablename__ = "outreach_drafts"
    __table_args__ = (Index("ix_outreach_drafts_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_reports.id")
    )
    qualification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("qualification_results.id")
    )

    # ── Strategy ──────────────────────────────────────────────────────
    strategy_channel: Mapped[str] = mapped_column(
        String(50), nullable=False, default="email"
    )
    strategy_urgency: Mapped[str] = mapped_column(
        String(50), nullable=False, default="This week"
    )
    strategy_reasoning: Mapped[str] = mapped_column(Text, default="")

    # ── Personalization Intelligence ──────────────────────────────────
    company_hook: Mapped[str] = mapped_column(Text, default="")
    detected_pain_point: Mapped[str] = mapped_column(Text, default="")
    flytbase_value_proposition: Mapped[str] = mapped_column(Text, default="")

    # ── Email Draft ───────────────────────────────────────────────────
    draft_subject: Mapped[str] = mapped_column(String(500), default="")
    draft_body: Mapped[str] = mapped_column(Text, default="")
    follow_up_suggestion: Mapped[str] = mapped_column(Text, default="")

    # ── Approval Lifecycle ────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_approval"
    )
    approval_notes: Mapped[str | None] = mapped_column(Text)
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Metadata ──────────────────────────────────────────────────────
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))

    # ── Relationships ────────────────────────────────────────────────
    task: Mapped[AgentTask] = relationship()
    company: Mapped[Company] = relationship()
    history: Mapped[list[OutreachHistory]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class CompanyIntelligenceBrief(TimestampMixin, Base):
    """Reviewable intelligence snapshot used before human outreach approval."""

    __tablename__ = "company_intelligence_briefs"
    __table_args__ = (
        Index("ix_company_intelligence_briefs_draft_id", "outreach_draft_id"),
        Index("ix_company_intelligence_briefs_company_id", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_drafts.id"), nullable=False, unique=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_reports.id")
    )
    qualification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("qualification_results.id")
    )
    brief_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(100),
        default="simulated_structured_intelligence",
        nullable=False,
    )


class OutreachHistory(TimestampMixin, Base):
    """Immutable record of an approved/sent outreach attempt.

    Snapshots the approved draft content so that historical records
    remain accurate even if the original draft is later modified.
    """

    __tablename__ = "outreach_history"
    __table_args__ = (Index("ix_outreach_history_lead_id", "lead_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_drafts.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))

    # ── Snapshot of what was approved/sent (immutable copy) ───────────
    sent_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    sent_body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft_approved"
    )

    # ── Approval metadata ────────────────────────────────────────────
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Response tracking (future) ───────────────────────────────────
    response_received: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    response_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # ── Relationships ────────────────────────────────────────────────
    draft: Mapped[OutreachDraft] = relationship(back_populates="history")


class InboundMessage(TimestampMixin, Base):
    """Inbound message with AI analysis.

    Stores the raw message, intent/sentiment/urgency analysis,
    extracted details, and any suggested reply. The message body
    is also mirrored to the Conversation table for unified history.
    """

    __tablename__ = "inbound_messages"
    __table_args__ = (Index("ix_inbound_messages_lead_id", "lead_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id")
    )

    # ── Sender ────────────────────────────────────────────────────────
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, default="email"
    )

    # ── Content ───────────────────────────────────────────────────────
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Lead/contact links ────────────────────────────────────────────
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))

    # ── Agent Analysis ────────────────────────────────────────────────
    intent: Mapped[str | None] = mapped_column(String(50))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    urgency: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column()

    extracted_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # ── Suggested Action ──────────────────────────────────────────────
    lead_action: Mapped[str | None] = mapped_column(String(50))
    suggested_status: Mapped[str | None] = mapped_column(String(50))
    suggested_reply_subject: Mapped[str | None] = mapped_column(String(500))
    suggested_reply_body: Mapped[str | None] = mapped_column(Text)
    follow_up_suggestion: Mapped[str | None] = mapped_column(Text)

    # ── Approval Lifecycle ────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_review"
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    # ── Metadata ──────────────────────────────────────────────────────
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))

    # ── Relationships ────────────────────────────────────────────────
    task: Mapped[AgentTask] = relationship()
    conversation: Mapped[Conversation | None] = relationship()


class PipelineStage(TimestampMixin, Base):
    """Configurable pipeline stage definition.

    Defines the BDR pipeline stages and their order.
    is_active allows disabling stages without removing data.
    """

    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))


class PipelineStatus(TimestampMixin, Base):
    """Per-lead pipeline position and history.

    The is_current record holds the lead's present stage.
    Historical records provide the full pipeline journey.
    """

    __tablename__ = "pipeline_status"
    __table_args__ = (
        Index("ix_pipeline_status_lead_stage", "lead_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_tasks.id"))

    # ── Pipeline Position ────────────────────────────────────────────
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Intelligence ─────────────────────────────────────────────────
    entered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="agent"
    )
    reason: Mapped[str | None] = mapped_column(Text)
    signal_summary: Mapped[str | None] = mapped_column(Text)
    recommended_next_action: Mapped[str | None] = mapped_column(Text)

    # ── Metadata ─────────────────────────────────────────────────────
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    # ── Relationships ────────────────────────────────────────────────
    lead: Mapped[Lead] = relationship()
    task: Mapped[AgentTask | None] = relationship()

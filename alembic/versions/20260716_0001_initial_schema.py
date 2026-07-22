"""Create ScoutOS operational foundation.

Revision ID: 20260716_0001
Revises:
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260716_0001"
down_revision = None
branch_labels = None
depends_on = None


def uuid_column(name: str, *args: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def upgrade() -> None:
    op.create_table(
        "companies",
        uuid_column("id", primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), unique=True),
        sa.Column("industry", sa.String(length=120)),
        sa.Column("employee_count", sa.Integer()),
        sa.Column(
            "profile_data",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "contacts",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("first_name", sa.String(length=100)),
        sa.Column("last_name", sa.String(length=100)),
        sa.Column("email", sa.String(length=320), unique=True),
        sa.Column("title", sa.String(length=255)),
        sa.Column(
            "profile_data",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "leads",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        uuid_column("contact_id", sa.ForeignKey("contacts.id")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("score", sa.Integer()),
        sa.Column("score_reasoning", sa.Text()),
        sa.Column("source", sa.String(length=100)),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_table(
        "agent_tasks",
        uuid_column("id", primary_key=True, nullable=False),
        sa.Column("agent_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        uuid_column("company_id", sa.ForeignKey("companies.id")),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        sa.Column(
            "input_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("output_data", postgresql.JSONB()),
        sa.Column(
            "requires_human_approval", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_tasks_status_type", "agent_tasks", ["status", "agent_type"])
    op.create_table(
        "agent_logs",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "research_reports",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id")),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "sources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("provider", sa.String(length=100)),
        sa.Column("model", sa.String(length=255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_research_reports_company_id", "research_reports", ["company_id"])
    op.create_table(
        "conversations",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id")),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        uuid_column("contact_id", sa.ForeignKey("contacts.id")),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=500)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_lead_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_research_reports_company_id", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_table("agent_logs")
    op.drop_index("ix_agent_tasks_status_type", table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_table("leads")
    op.drop_table("contacts")
    op.drop_table("companies")

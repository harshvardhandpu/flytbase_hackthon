"""Add inbound messages, pipeline stages, and pipeline status for Phase 5.

Revision ID: 20260720_0001
Revises: 20260718_0001
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260720_0001"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None


def uuid_column(name: str, *args: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def upgrade() -> None:
    # -- inbound_messages --------------------------------------------------
    op.create_table(
        "inbound_messages",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id"), nullable=False),
        uuid_column("conversation_id", sa.ForeignKey("conversations.id")),
        sa.Column("from_email", sa.String(length=320), nullable=False),
        sa.Column("from_name", sa.String(length=255)),
        sa.Column("channel", sa.String(length=50), nullable=False,
                  server_default="email"),
        sa.Column("subject", sa.String(length=500)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        uuid_column("contact_id", sa.ForeignKey("contacts.id")),
        uuid_column("company_id", sa.ForeignKey("companies.id")),
        sa.Column("intent", sa.String(length=50)),
        sa.Column("sentiment", sa.String(length=20)),
        sa.Column("urgency", sa.String(length=20)),
        sa.Column("confidence", sa.Float()),
        sa.Column("extracted_details", postgresql.JSONB()),
        sa.Column("lead_action", sa.String(length=50)),
        sa.Column("suggested_status", sa.String(length=50)),
        sa.Column("suggested_reply_subject", sa.String(length=500)),
        sa.Column("suggested_reply_body", sa.Text()),
        sa.Column("follow_up_suggestion", sa.Text()),
        sa.Column("status", sa.String(length=50), nullable=False,
                  server_default="pending_review"),
        sa.Column("reviewed_by", sa.String(length=255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text()),
        sa.Column("provider", sa.String(length=100)),
        sa.Column("model", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_inbound_messages_lead_id", "inbound_messages", ["lead_id"]
    )

    # -- pipeline_stages ---------------------------------------------------
    op.create_table(
        "pipeline_stages",
        uuid_column("id", primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("color", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Seed default pipeline stages
    stages_sql = (
        "INSERT INTO pipeline_stages "
        "(id, name, display_name, description, "
        '"order", is_active, color) VALUES '
        "(gen_random_uuid(), 'new', 'New Lead', "
        "'Lead just entered the pipeline', 1, true, 'blue'), "
        "(gen_random_uuid(), 'researching', 'Researching', "
        "'BDR researching the company', 2, true, 'indigo'), "
        "(gen_random_uuid(), 'qualified', 'Qualified', "
        "'Lead has been qualified with a score', 3, true, 'cyan'), "
        "(gen_random_uuid(), 'outreach', 'Outreach', "
        "'Outreach in progress', 4, true, 'teal'), "
        "(gen_random_uuid(), 'meeting_scheduled', 'Meeting Scheduled', "
        "'Demo or meeting confirmed', 5, true, 'green'), "
        "(gen_random_uuid(), 'negotiation', 'Negotiation', "
        "'Active deal negotiation', 6, true, 'yellow'), "
        "(gen_random_uuid(), 'closed_won', 'Closed Won', "
        "'Deal closed successfully', 7, true, 'emerald'), "
        "(gen_random_uuid(), 'closed_lost', 'Closed Lost', "
        "'Deal lost', 8, true, 'red')"
    )
    op.execute(stages_sql)

    # -- pipeline_status ---------------------------------------------------
    op.create_table(
        "pipeline_status",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id"), nullable=False),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id")),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("entered_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("entered_by", sa.String(length=50), nullable=False,
                  server_default="agent"),
        sa.Column("reason", sa.Text()),
        sa.Column("signal_summary", sa.Text()),
        sa.Column("recommended_next_action", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_pipeline_status_lead_stage",
        "pipeline_status",
        ["lead_id", "is_current"],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_status_lead_stage", table_name="pipeline_status")
    op.drop_table("pipeline_status")
    op.drop_table("pipeline_stages")
    op.drop_index("ix_inbound_messages_lead_id", table_name="inbound_messages")
    op.drop_table("inbound_messages")

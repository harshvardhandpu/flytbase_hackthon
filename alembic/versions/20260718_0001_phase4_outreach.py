"""Add outreach draft and history tables for Phase 4.

Revision ID: 20260718_0001
Revises: 20260717_0001
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260718_0001"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None


def uuid_column(name: str, *args: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def upgrade() -> None:
    # ── outreach_drafts ─────────────────────────────────────────────────
    op.create_table(
        "outreach_drafts",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id"), nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        uuid_column("report_id", sa.ForeignKey("research_reports.id")),
        uuid_column("qualification_id", sa.ForeignKey("qualification_results.id")),

        sa.Column("strategy_channel", sa.String(length=50), nullable=False,
                  server_default="email"),
        sa.Column("strategy_urgency", sa.String(length=50), nullable=False,
                  server_default="This week"),
        sa.Column("strategy_reasoning", sa.Text(), server_default=""),

        sa.Column("company_hook", sa.Text(), server_default=""),
        sa.Column("detected_pain_point", sa.Text(), server_default=""),
        sa.Column("flytbase_value_proposition", sa.Text(), server_default=""),

        sa.Column("draft_subject", sa.String(length=500), server_default=""),
        sa.Column("draft_body", sa.Text(), server_default=""),
        sa.Column("follow_up_suggestion", sa.Text(), server_default=""),

        sa.Column("status", sa.String(length=50), nullable=False,
                  server_default="pending_approval"),
        sa.Column("approval_notes", sa.Text()),
        sa.Column("rejected_reason", sa.Text()),
        sa.Column("approved_by", sa.String(length=255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),

        sa.Column("provider", sa.String(length=100)),
        sa.Column("model", sa.String(length=255)),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_outreach_drafts_status", "outreach_drafts", ["status"]
    )

    # ── outreach_history ────────────────────────────────────────────────
    op.create_table(
        "outreach_history",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("draft_id", sa.ForeignKey("outreach_drafts.id"),
                    nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),

        sa.Column("sent_subject", sa.String(length=500), nullable=False),
        sa.Column("sent_body", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False,
                  server_default="draft_approved"),

        sa.Column("approved_by", sa.String(length=255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),

        sa.Column("response_received", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("response_data", postgresql.JSONB()),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_outreach_history_lead_id", "outreach_history", ["lead_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_history_lead_id", table_name="outreach_history")
    op.drop_table("outreach_history")
    op.drop_index("ix_outreach_drafts_status", table_name="outreach_drafts")
    op.drop_table("outreach_drafts")

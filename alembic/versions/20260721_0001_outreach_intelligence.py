"""Add reusable company intelligence briefs for outreach approval.

Revision ID: 20260721_0001
Revises: 20260720_0001
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260721_0001"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_intelligence_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("outreach_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outreach_drafts.id"), nullable=False, unique=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_reports.id")),
        sa.Column("qualification_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("qualification_results.id")),
        sa.Column("brief_data", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="simulated_structured_intelligence"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_intelligence_briefs_draft_id", "company_intelligence_briefs", ["outreach_draft_id"])
    op.create_index("ix_company_intelligence_briefs_company_id", "company_intelligence_briefs", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_company_intelligence_briefs_company_id", table_name="company_intelligence_briefs")
    op.drop_index("ix_company_intelligence_briefs_draft_id", table_name="company_intelligence_briefs")
    op.drop_table("company_intelligence_briefs")

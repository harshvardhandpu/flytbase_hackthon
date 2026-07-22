"""Add ICP config and qualification result tables for Phase 3.

Revision ID: 20260717_0001
Revises: 20260716_0001
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260717_0001"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def uuid_column(name: str, *args: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def upgrade() -> None:
    # ── icp_configs ────────────────────────────────────────────────────
    op.create_table(
        "icp_configs",
        uuid_column("id", primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("industries", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("min_employees", sa.Integer()),
        sa.Column("max_employees", sa.Integer()),
        sa.Column("locations", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("technology_signals", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False,
                  server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── qualification_results ──────────────────────────────────────────
    op.create_table(
        "qualification_results",
        uuid_column("id", primary_key=True, nullable=False),
        uuid_column("task_id", sa.ForeignKey("agent_tasks.id"), nullable=False),
        uuid_column("company_id", sa.ForeignKey("companies.id"), nullable=False),
        uuid_column("lead_id", sa.ForeignKey("leads.id")),
        uuid_column("report_id", sa.ForeignKey("research_reports.id")),
        uuid_column("icp_config_id", sa.ForeignKey("icp_configs.id")),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("icp_match_score", sa.Integer(), nullable=False),
        sa.Column("buying_signal_score", sa.Integer(), nullable=False),
        sa.Column("company_fit_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("reasons", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("risks", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_urgency", sa.String(length=50)),
        sa.Column("recommended_sales_angle", sa.Text()),
        sa.Column("icp_inline_config", postgresql.JSONB()),
        sa.Column("provider", sa.String(length=100)),
        sa.Column("model", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_qualification_task_id", "qualification_results", ["task_id"]
    )

    # ── seed default ICP config ────────────────────────────────────────
    op.execute(
        sa.text(
            """INSERT INTO icp_configs (id, name, description, industries,
                min_employees, max_employees, locations, technology_signals,
                is_active, version)
            VALUES (
                '00000000-0000-0000-0000-000000000001',
                'Default ICP',
                'Default ICP for drone technology, SaaS, and automation companies.',
                '["Drone Technology", "SaaS", "Automation", "Enterprise Software"]',
                10, 500,
                '["US", "EU", "IN"]',
                '["drone", "DJI", "automation", "fleet management", "IoT"]',
                true, 1
            )"""
        )
    )


def downgrade() -> None:
    op.drop_index("ix_qualification_task_id", table_name="qualification_results")
    op.drop_table("qualification_results")
    op.drop_table("icp_configs")

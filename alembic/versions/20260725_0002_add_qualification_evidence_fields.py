"""Add evidence-backed scoring fields to qualification_results.

Adds:
- pain_alignment_score    (Integer, not null, default 0)
- evidence_based_reasons  (JSONB, not null, default [])
- qualification_summary   (Text, not null, default '')

Revision ID: 20260725_0002
Revises:      20260716_0001
Create Date:  2026-07-25
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260725_0002"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qualification_results",
        sa.Column(
            "pain_alignment_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "qualification_results",
        sa.Column(
            "evidence_based_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "qualification_results",
        sa.Column(
            "qualification_summary",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("qualification_results", "qualification_summary")
    op.drop_column("qualification_results", "evidence_based_reasons")
    op.drop_column("qualification_results", "pain_alignment_score")

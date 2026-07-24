"""Add citations and intelligence_metadata columns to research_reports

Revision ID: 20260723_0001
Revises: 20260721_0001
Create Date: 2026-07-23 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260723_0001"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_reports",
        sa.Column("citations", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "research_reports",
        sa.Column("intelligence_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_reports", "intelligence_metadata")
    op.drop_column("research_reports", "citations")

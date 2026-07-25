"""Merge migration heads.

Reconciles the branch from 20260723_0001 (main Phase 3-5 chain)
with the branch from 20260725_0002 (qualification evidence fields).

Both branches represent additive schema changes that do not conflict.
This merge has no upgrade/downgrade operations of its own; it simply
establishes a single linear chain for future migrations.

Revision ID: 20260725_0003
Revises:     20260723_0001, 20260725_0002
Create Date: 2026-07-25
"""

from alembic import op

revision = "20260725_0003"
down_revision = ("20260723_0001", "20260725_0002")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge branch heads — no schema changes required."""
    pass


def downgrade() -> None:
    """Reverse merge — no schema changes to revert."""
    pass

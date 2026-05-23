"""Add auto_off_at to ghost_sessions

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ghost_sessions "
        "ADD COLUMN IF NOT EXISTS auto_off_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ghost_sessions "
        "DROP COLUMN IF EXISTS auto_off_at"
    )

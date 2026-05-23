"""Add excluded_contact_ids and excluded_labels to ghost_sessions

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ghost_sessions "
        "ADD COLUMN IF NOT EXISTS excluded_contact_ids BIGINT[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE ghost_sessions "
        "ADD COLUMN IF NOT EXISTS excluded_labels TEXT[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ghost_sessions DROP COLUMN IF EXISTS excluded_contact_ids")
    op.execute("ALTER TABLE ghost_sessions DROP COLUMN IF EXISTS excluded_labels")

"""add username columns to contacts, tasks, ghost_inquiries

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS username VARCHAR(256)")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assignee_username VARCHAR(256)")
    op.execute("ALTER TABLE ghost_inquiries ADD COLUMN IF NOT EXISTS caller_username VARCHAR(256)")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS username")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS assignee_username")
    op.execute("ALTER TABLE ghost_inquiries DROP COLUMN IF EXISTS caller_username")

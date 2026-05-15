"""add reminder_time, is_personal, reminder_fired to tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_time TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_fired BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS reminder_time")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS is_personal")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS reminder_fired")

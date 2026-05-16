"""add phone, team_label, synced_from, tg names, email to contacts

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS phone VARCHAR(32)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS team_label VARCHAR(64)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS synced_from VARCHAR(32)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS tg_first_name VARCHAR(128)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS tg_last_name VARCHAR(128)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ")


def downgrade() -> None:
    for col in ("phone", "team_label", "synced_from", "tg_first_name", "tg_last_name", "email", "last_synced_at"):
        op.execute(f"ALTER TABLE contacts DROP COLUMN IF EXISTS {col}")

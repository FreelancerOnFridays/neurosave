"""Add CRM fields to contacts table

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS crm_status VARCHAR(32)")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS notes TEXT")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS next_action TEXT")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS next_action_date TIMESTAMPTZ")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS importance INTEGER NOT NULL DEFAULT 3")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS crm_status")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS next_action")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS next_action_date")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS importance")

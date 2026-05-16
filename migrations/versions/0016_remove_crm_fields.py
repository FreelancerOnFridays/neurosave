"""Remove CRM columns from contacts table

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE contacts
            DROP COLUMN IF EXISTS crm_status,
            DROP COLUMN IF EXISTS notes,
            DROP COLUMN IF EXISTS next_action,
            DROP COLUMN IF EXISTS next_action_date,
            DROP COLUMN IF EXISTS importance
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE contacts
            ADD COLUMN IF NOT EXISTS crm_status VARCHAR(32),
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS next_action TEXT,
            ADD COLUMN IF NOT EXISTS next_action_date TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS importance INTEGER NOT NULL DEFAULT 3
    """)

"""Add business_connection_id and last_brief_date to user_settings

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS business_connection_id VARCHAR(256), "
        "ADD COLUMN IF NOT EXISTS last_brief_date VARCHAR(16)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings "
        "DROP COLUMN IF EXISTS business_connection_id, "
        "DROP COLUMN IF EXISTS last_brief_date"
    )

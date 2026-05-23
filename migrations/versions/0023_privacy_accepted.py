"""Add privacy_accepted_at to user_settings

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ"
    )
    # Existing users are treated as having accepted (they were using the bot before this policy)
    op.execute(
        "UPDATE user_settings SET privacy_accepted_at = created_at "
        "WHERE privacy_accepted_at IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_settings "
        "DROP COLUMN IF EXISTS privacy_accepted_at"
    )

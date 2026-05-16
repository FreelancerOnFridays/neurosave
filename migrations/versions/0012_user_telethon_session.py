"""per-user telethon session storage

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS telethon_session TEXT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS telethon_session")

"""per-user settings table

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            owner_id BIGINT PRIMARY KEY,
            language VARCHAR(8) NOT NULL DEFAULT 'ru',
            timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
            brief_time VARCHAR(8) NOT NULL DEFAULT '09:00',
            brief_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            theme VARCHAR(16) NOT NULL DEFAULT 'auto',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_settings")

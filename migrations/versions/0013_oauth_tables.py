"""oauth_tokens table for external integrations

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY,
            owner_id BIGINT NOT NULL,
            provider VARCHAR(32) NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_expiry TIMESTAMPTZ,
            scopes TEXT,
            email VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (owner_id, provider)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_oauth_tokens_owner_id ON oauth_tokens (owner_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_tokens")

"""Add integration_configs table for storing per-user integration settings

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_configs (
            owner_id BIGINT NOT NULL,
            key VARCHAR(64) NOT NULL,
            value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (owner_id, key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_configs")

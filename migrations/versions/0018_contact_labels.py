"""Add labels array column to contacts

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS labels TEXT[] NOT NULL DEFAULT '{}'")
    op.execute("UPDATE contacts SET labels = ARRAY[team_label] WHERE team_label IS NOT NULL AND cardinality(labels) = 0")


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS labels")

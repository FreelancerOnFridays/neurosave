"""Add Normal value to InquiryCategory enum

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE inquirycategory ADD VALUE IF NOT EXISTS 'Normal'")


def downgrade() -> None:
    pass  # PostgreSQL does not support removing enum values

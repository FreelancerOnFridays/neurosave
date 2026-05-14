"""add business_connection_id to tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("business_connection_id", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "business_connection_id")

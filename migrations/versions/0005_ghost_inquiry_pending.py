"""add ghost_pending to ghost_inquiries

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ghost_inquiries",
        sa.Column("ghost_pending", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("ghost_inquiries", "ghost_pending")

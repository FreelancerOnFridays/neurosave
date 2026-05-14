"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assignee_name", sa.String(256), nullable=True),
        sa.Column("assignee_user_id", sa.BigInteger(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "done", "cancelled", name="taskstatus"),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_name", sa.String(256), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_owner_id", "messages", ["owner_id"])
    op.create_index("ix_messages_timestamp", "messages", ["timestamp"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("is_vip", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_owner_id", "contacts", ["owner_id"])

    op.create_table(
        "ghost_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("away_message", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
    )
    op.create_index("ix_ghost_sessions_owner_id", "ghost_sessions", ["owner_id"])

    op.create_table(
        "ghost_inquiries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("caller_id", sa.BigInteger(), nullable=False),
        sa.Column("caller_name", sa.String(256), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "category",
            sa.Enum("Urgent", "Sales", "Team", "Spam", name="inquirycategory"),
            nullable=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ghost_inquiries_owner_id", "ghost_inquiries", ["owner_id"])


def downgrade() -> None:
    op.drop_table("ghost_inquiries")
    op.drop_table("ghost_sessions")
    op.drop_table("contacts")
    op.drop_table("messages")
    op.drop_table("tasks")
    op.execute("DROP TYPE IF EXISTS inquirycategory")
    op.execute("DROP TYPE IF EXISTS taskstatus")

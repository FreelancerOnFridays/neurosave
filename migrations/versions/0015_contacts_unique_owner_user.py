"""Add UNIQUE constraint on (owner_id, user_id) in contacts, dedup existing rows

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-16
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove duplicate (owner_id, user_id) pairs, keeping the row with the highest id
    op.execute("""
        DELETE FROM contacts
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM contacts
            GROUP BY owner_id, user_id
        )
    """)
    # Now add the unique constraint
    op.execute("""
        ALTER TABLE contacts
        ADD CONSTRAINT uq_contacts_owner_user UNIQUE (owner_id, user_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE contacts DROP CONSTRAINT IF EXISTS uq_contacts_owner_user")

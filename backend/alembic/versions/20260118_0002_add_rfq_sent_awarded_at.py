"""add missing rfqs sent/awarded timestamps

Revision ID: 20260118_0002_add_rfq_sent_awarded_at
Revises: 20260118_0001_add_partially_hedged_to_enums
Create Date: 2026-01-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260118_0002_add_rfq_sent_awarded_at"
down_revision = "20260118_0001_add_partially_hedged_to_enums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE rfqs ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ NULL")
        op.execute("ALTER TABLE rfqs ADD COLUMN IF NOT EXISTS awarded_at TIMESTAMPTZ NULL")
        return

    op.add_column("rfqs", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rfqs", sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE rfqs DROP COLUMN IF EXISTS awarded_at")
        op.execute("ALTER TABLE rfqs DROP COLUMN IF EXISTS sent_at")
        return

    op.drop_column("rfqs", "awarded_at")
    op.drop_column("rfqs", "sent_at")

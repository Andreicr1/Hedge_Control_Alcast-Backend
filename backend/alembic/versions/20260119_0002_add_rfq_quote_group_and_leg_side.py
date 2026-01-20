"""add quote_group_id and leg_side to rfq_quotes

Revision ID: 20260119_0002_add_rfq_quote_group_and_leg_side
Revises: 20260119_0001_add_treasury_decisions
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260119_0002_add_rfq_quote_group_and_leg_side"
down_revision = "20260119_0001_add_treasury_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rfq_quotes",
        sa.Column("quote_group_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "rfq_quotes",
        sa.Column("leg_side", sa.String(length=8), nullable=True),
    )

    op.create_index(
        "ix_rfq_quotes_quote_group_id",
        "rfq_quotes",
        ["quote_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_rfq_quotes_quote_group_id", table_name="rfq_quotes")
    op.drop_column("rfq_quotes", "leg_side")
    op.drop_column("rfq_quotes", "quote_group_id")

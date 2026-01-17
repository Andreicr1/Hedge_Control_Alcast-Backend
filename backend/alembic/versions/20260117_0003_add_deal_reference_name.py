"""add deal reference name

Revision ID: 20260117_0003_add_deal_reference_name
Revises: 20260117_0002_add_deals_contracts_search_indexes
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260117_0003_add_deal_reference_name"
down_revision = "20260117_0002_add_deals_contracts_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("reference_name", sa.String(length=255), nullable=True))
    op.create_index("ix_deals_reference_name", "deals", ["reference_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_deals_reference_name", table_name="deals")
    op.drop_column("deals", "reference_name")

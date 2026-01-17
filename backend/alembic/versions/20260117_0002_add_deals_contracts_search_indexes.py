"""add deals/contracts search indexes

Revision ID: 20260117_0002_add_deals_contracts_search_indexes
Revises: 20260117_0001_add_masterdata_search_indexes
Create Date: 2026-01-17
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260117_0002_add_deals_contracts_search_indexes"
down_revision = "20260117_0001_add_masterdata_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deals
    op.create_index("ix_deals_deal_uuid", "deals", ["deal_uuid"], unique=False)
    op.create_index("ix_deals_commodity", "deals", ["commodity"], unique=False)
    op.create_index("ix_deals_status", "deals", ["status"], unique=False)
    op.create_index("ix_deals_lifecycle_status", "deals", ["lifecycle_status"], unique=False)

    # Contracts
    op.create_index("ix_contracts_status", "contracts", ["status"], unique=False)
    op.create_index("ix_contracts_quote_group_id", "contracts", ["quote_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_contracts_quote_group_id", table_name="contracts")
    op.drop_index("ix_contracts_status", table_name="contracts")

    op.drop_index("ix_deals_lifecycle_status", table_name="deals")
    op.drop_index("ix_deals_status", table_name="deals")
    op.drop_index("ix_deals_commodity", table_name="deals")
    op.drop_index("ix_deals_deal_uuid", table_name="deals")

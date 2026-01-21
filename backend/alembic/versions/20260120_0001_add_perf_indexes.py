"""add performance indexes

Revision ID: 20260120_0001_add_perf_indexes
Revises: 20260119_0002_add_rfq_quote_group_and_leg_side
Create Date: 2026-01-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260120_0001_add_perf_indexes"
down_revision = "20260119_0002_add_rfq_quote_group_and_leg_side"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_contracts_settlement_date",
        "contracts",
        ["settlement_date"],
    )
    op.create_index(
        "ix_exposures_status",
        "exposures",
        ["status"],
    )
    op.create_index(
        "ix_exposures_status_source_type",
        "exposures",
        ["status", "source_type"],
    )
    op.create_index(
        "ix_contracts_deal_id_settlement_date",
        "contracts",
        ["deal_id", "settlement_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_contracts_deal_id_settlement_date", table_name="contracts")
    op.drop_index("ix_exposures_status_source_type", table_name="exposures")
    op.drop_index("ix_exposures_status", table_name="exposures")
    op.drop_index("ix_contracts_settlement_date", table_name="contracts")

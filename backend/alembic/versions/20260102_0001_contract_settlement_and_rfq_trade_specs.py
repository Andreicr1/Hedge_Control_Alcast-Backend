"""Add Contract settlement_date and RFQ trade_specs (rfq_engine parity)

Revision ID: 20260102_0001_contract_settlement_and_rfq_trade_specs
Revises: 20250111_0009_rfq_channel_message
Create Date: 2026-01-02
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260102_0001_contract_settlement_and_rfq_trade_specs"
down_revision = "20250111_0009_rfq_channel_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect

    op.add_column("rfqs", sa.Column("trade_specs", sa.JSON(), nullable=True))

    # Only add contract columns if the contracts table exists
    conn = op.get_bind()
    inspector = inspect(conn)
    if "contracts" in inspector.get_table_names():
        op.add_column("contracts", sa.Column("settlement_date", sa.Date(), nullable=True))
        op.add_column("contracts", sa.Column("settlement_meta", sa.JSON(), nullable=True))
        op.create_index("idx_contracts_settlement_date", "contracts", ["settlement_date"])


def downgrade() -> None:
    from sqlalchemy import inspect

    # Only drop contract columns if the contracts table exists
    conn = op.get_bind()
    inspector = inspect(conn)
    if "contracts" in inspector.get_table_names():
        op.drop_index("idx_contracts_settlement_date", table_name="contracts")
        op.drop_column("contracts", "settlement_meta")
        op.drop_column("contracts", "settlement_date")

    op.drop_column("rfqs", "trade_specs")

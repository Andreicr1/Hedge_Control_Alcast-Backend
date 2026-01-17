"""Add contracts table

Revision ID: 20260111_0003_add_contracts_table
Revises: 20260111_0002_add_supplier_customer_columns
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260111_0003_add_contracts_table"
down_revision = "20260111_0002_add_supplier_customer_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Create contracts table if it doesn't exist
    if 'contracts' not in inspector.get_table_names():
        op.create_table(
            'contracts',
            sa.Column('contract_id', sa.String(36), primary_key=True),
            sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False, index=True),
            sa.Column('rfq_id', sa.Integer(), sa.ForeignKey('rfqs.id'), nullable=False, index=True),
            sa.Column('counterparty_id', sa.Integer(), sa.ForeignKey('counterparties.id'), nullable=True),
            sa.Column('status', sa.String(32), nullable=False, server_default='active'),
            sa.Column('trade_index', sa.Integer(), nullable=True),
            sa.Column('quote_group_id', sa.String(64), nullable=True),
            sa.Column('trade_snapshot', sa.JSON(), nullable=False),
            sa.Column('settlement_date', sa.Date(), nullable=True),
            sa.Column('settlement_meta', sa.JSON(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('idx_contracts_settlement_date', 'contracts', ['settlement_date'])


def downgrade() -> None:
    op.drop_index('idx_contracts_settlement_date', table_name='contracts')
    op.drop_table('contracts')

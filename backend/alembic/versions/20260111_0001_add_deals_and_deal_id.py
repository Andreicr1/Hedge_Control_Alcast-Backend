"""Add deals table and deal_id columns to PO/SO

Revision ID: 20260111_0001_add_deals_and_deal_id
Revises: 20260102_0001_contract_settlement_and_rfq_trade_specs
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260111_0001_add_deals_and_deal_id"
down_revision = "20260102_0001_contract_settlement_and_rfq_trade_specs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    dialect = conn.dialect.name
    
    # Check if deals table already exists
    if 'deals' in inspector.get_table_names():
        # Table exists, just check for missing columns
        pass
    else:
        # Create deals table (enums will be created automatically with checkfirst)
        op.create_table(
            'deals',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('deal_uuid', sa.String(36), unique=True, nullable=False),
            sa.Column('commodity', sa.String(255), nullable=True),
            sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
            sa.Column('status', sa.String(32), nullable=False, server_default='open'),
            sa.Column('lifecycle_status', sa.String(32), nullable=False, server_default='open'),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create deal_links table if it doesn't exist
    if 'deal_links' not in inspector.get_table_names():
        op.create_table(
            'deal_links',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False),
            sa.Column('entity_type', sa.String(32), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('direction', sa.String(16), nullable=False),
            sa.Column('quantity_mt', sa.Float(), nullable=True),
            sa.Column('allocation_type', sa.String(16), nullable=False, server_default='auto'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_deal_links_deal_id', 'deal_links', ['deal_id'])
        op.create_index('ix_deal_links_entity_id', 'deal_links', ['entity_id'])
    
    # Create deal_pnl_snapshots table if it doesn't exist
    if 'deal_pnl_snapshots' not in inspector.get_table_names():
        op.create_table(
            'deal_pnl_snapshots',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('physical_revenue', sa.Float(), nullable=False, server_default='0'),
            sa.Column('physical_cost', sa.Float(), nullable=False, server_default='0'),
            sa.Column('hedge_pnl_realized', sa.Float(), nullable=False, server_default='0'),
            sa.Column('hedge_pnl_mtm', sa.Float(), nullable=False, server_default='0'),
            sa.Column('net_pnl', sa.Float(), nullable=False, server_default='0'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_deal_pnl_snapshots_deal_id', 'deal_pnl_snapshots', ['deal_id'])
    
    # Check existing columns in purchase_orders
    po_columns = [c['name'] for c in inspector.get_columns('purchase_orders')]
    if 'deal_id' not in po_columns:
        if dialect == 'sqlite':
            with op.batch_alter_table('purchase_orders') as batch_op:
                batch_op.add_column(sa.Column('deal_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    'fk_purchase_orders_deal_id__deals_id',
                    'deals',
                    ['deal_id'],
                    ['id'],
                )
        else:
            op.add_column('purchase_orders', sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=True))
        op.create_index('ix_purchase_orders_deal_id', 'purchase_orders', ['deal_id'])
    
    # Check existing columns in sales_orders
    so_columns = [c['name'] for c in inspector.get_columns('sales_orders')]
    if 'deal_id' not in so_columns:
        if dialect == 'sqlite':
            with op.batch_alter_table('sales_orders') as batch_op:
                batch_op.add_column(sa.Column('deal_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    'fk_sales_orders_deal_id__deals_id',
                    'deals',
                    ['deal_id'],
                    ['id'],
                )
        else:
            op.add_column('sales_orders', sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=True))
        op.create_index('ix_sales_orders_deal_id', 'sales_orders', ['deal_id'])


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    # Drop deal_id from purchase_orders
    op.drop_index('ix_purchase_orders_deal_id', table_name='purchase_orders')
    if dialect == 'sqlite':
        with op.batch_alter_table('purchase_orders') as batch_op:
            batch_op.drop_constraint('fk_purchase_orders_deal_id__deals_id', type_='foreignkey')
            batch_op.drop_column('deal_id')
    else:
        op.drop_column('purchase_orders', 'deal_id')
    
    # Drop deal_id from sales_orders
    op.drop_index('ix_sales_orders_deal_id', table_name='sales_orders')
    if dialect == 'sqlite':
        with op.batch_alter_table('sales_orders') as batch_op:
            batch_op.drop_constraint('fk_sales_orders_deal_id__deals_id', type_='foreignkey')
            batch_op.drop_column('deal_id')
    else:
        op.drop_column('sales_orders', 'deal_id')
    
    # Drop deal_pnl_snapshots table
    op.drop_table('deal_pnl_snapshots')
    
    # Drop deal_links table
    op.drop_table('deal_links')
    
    # Drop deals table
    op.drop_table('deals')
    
    # Drop enums
    if dialect == 'postgresql':
        sa.Enum(name='dealallocationtype').drop(op.get_bind(), checkfirst=True)
        sa.Enum(name='dealdirection').drop(op.get_bind(), checkfirst=True)
        sa.Enum(name='dealentitytype').drop(op.get_bind(), checkfirst=True)
        sa.Enum(name='deallifecyclestatus').drop(op.get_bind(), checkfirst=True)
        sa.Enum(name='dealstatus').drop(op.get_bind(), checkfirst=True)

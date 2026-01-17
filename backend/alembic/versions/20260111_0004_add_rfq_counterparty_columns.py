"""Add missing columns to rfqs and counterparties tables

Revision ID: 20260111_0004_add_rfq_counterparty_columns
Revises: 20260111_0003_add_contracts_table
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260111_0004_add_rfq_counterparty_columns"
down_revision = "20260111_0003_add_contracts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    dialect = conn.dialect.name
    
    # Add missing columns to rfqs table
    rfq_columns = [c['name'] for c in inspector.get_columns('rfqs')]
    
    if 'deal_id' not in rfq_columns:
        if dialect == 'sqlite':
            with op.batch_alter_table('rfqs') as batch_op:
                batch_op.add_column(sa.Column('deal_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    'fk_rfqs_deal_id__deals_id',
                    'deals',
                    ['deal_id'],
                    ['id'],
                )
        else:
            op.add_column('rfqs', sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=True))
        op.create_index('ix_rfqs_deal_id', 'rfqs', ['deal_id'])
    
    if 'message_text' not in rfq_columns:
        op.add_column('rfqs', sa.Column('message_text', sa.Text(), nullable=True))
    
    # Check counterparties table columns
    cp_columns = [c['name'] for c in inspector.get_columns('counterparties')]
    
    counterparty_columns_to_add = [
        ('code', sa.String(64)),
        ('contact_email', sa.String(255)),
        ('contact_phone', sa.String(64)),
        ('address_line', sa.String(255)),
        ('city', sa.String(128)),
        ('state', sa.String(8)),
        ('country', sa.String(64)),
        ('postal_code', sa.String(32)),
        ('tax_id', sa.String(32)),
        ('tax_id_type', sa.String(32)),
        ('risk_rating', sa.String(64)),
        ('credit_limit', sa.Float()),
        ('credit_score', sa.Integer()),
        ('kyc_status', sa.String(32)),
        ('kyc_notes', sa.Text()),
        ('payment_terms', sa.String(128)),
        ('base_currency', sa.String(8)),
        ('notes', sa.Text()),
    ]
    
    for col_name, col_type in counterparty_columns_to_add:
        if col_name not in cp_columns:
            op.add_column('counterparties', sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.drop_index('ix_rfqs_deal_id', table_name='rfqs')
    if dialect == 'sqlite':
        with op.batch_alter_table('rfqs') as batch_op:
            batch_op.drop_constraint('fk_rfqs_deal_id__deals_id', type_='foreignkey')
            batch_op.drop_column('deal_id')
            batch_op.drop_column('message_text')
    else:
        op.drop_column('rfqs', 'deal_id')
        op.drop_column('rfqs', 'message_text')
    
    counterparty_columns = [
        'code', 'contact_email', 'contact_phone', 'address_line', 'city',
        'state', 'country', 'postal_code', 'tax_id', 'tax_id_type',
        'risk_rating', 'credit_limit', 'credit_score', 'kyc_status',
        'kyc_notes', 'payment_terms', 'base_currency', 'notes'
    ]
    for col in counterparty_columns:
        try:
            op.drop_column('counterparties', col)
        except Exception:
            pass

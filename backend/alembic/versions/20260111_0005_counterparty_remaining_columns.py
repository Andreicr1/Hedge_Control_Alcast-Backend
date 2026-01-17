"""Add remaining columns to counterparties table

Revision ID: 20260111_0005_counterparty_remaining_columns
Revises: 20260111_0004_add_rfq_counterparty_columns
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260111_0005_counterparty_remaining_columns"
down_revision = "20260111_0004_add_rfq_counterparty_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    dialect = conn.dialect.name
    
    # Check counterparties table columns
    cp_columns = [c['name'] for c in inspector.get_columns('counterparties')]
    
    columns_to_add = [
        ('trade_name', sa.String(255)),
        ('legal_name', sa.String(255)),
        ('entity_type', sa.String(64)),
        ('country_incorporation', sa.String(64)),
        ('country_operation', sa.String(64)),
        ('tax_id_country', sa.String(32)),
        ('sanctions_flag', sa.Boolean()),
        ('internal_notes', sa.Text()),
    ]
    
    for col_name, col_type in columns_to_add:
        if col_name not in cp_columns:
            op.add_column('counterparties', sa.Column(col_name, col_type, nullable=True))
    
    # Also fix state column length (model has 64, table has 8)
    # ALTER column state type to varchar(64)
    if dialect == 'sqlite':
        with op.batch_alter_table('counterparties') as batch_op:
            batch_op.alter_column('state', type_=sa.String(64), existing_type=sa.String(8), existing_nullable=True)
    else:
        op.alter_column('counterparties', 'state', type_=sa.String(64), existing_type=sa.String(8), existing_nullable=True)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    columns_to_remove = [
        'trade_name', 'legal_name', 'entity_type', 'country_incorporation',
        'country_operation', 'tax_id_country', 'sanctions_flag', 'internal_notes'
    ]
    for col in columns_to_remove:
        try:
            op.drop_column('counterparties', col)
        except Exception:
            pass
    
    if dialect == 'sqlite':
        with op.batch_alter_table('counterparties') as batch_op:
            batch_op.alter_column('state', type_=sa.String(8), existing_type=sa.String(64), existing_nullable=True)
    else:
        op.alter_column('counterparties', 'state', type_=sa.String(8), existing_type=sa.String(64), existing_nullable=True)

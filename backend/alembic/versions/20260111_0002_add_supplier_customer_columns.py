"""Add missing columns to suppliers and customers tables

Revision ID: 20260111_0002_add_supplier_customer_columns
Revises: 20260111_0001_add_deals_and_deal_id
Create Date: 2026-01-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260111_0002_add_supplier_customer_columns"
down_revision = "20260111_0001_add_deals_and_deal_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Add missing columns to suppliers table
    supplier_columns = [c['name'] for c in inspector.get_columns('suppliers')]
    
    columns_to_add_suppliers = [
        ('trade_name', sa.String(255)),
        ('entity_type', sa.String(64)),
        ('tax_id_type', sa.String(32)),
        ('tax_id_country', sa.String(32)),
        ('country', sa.String(64)),
        ('country_incorporation', sa.String(64)),
        ('country_operation', sa.String(64)),
        ('country_residence', sa.String(64)),
        ('base_currency', sa.String(8)),
        ('payment_terms', sa.String(128)),
        ('risk_rating', sa.String(64)),
        ('sanctions_flag', sa.Boolean()),
        ('internal_notes', sa.Text()),
    ]
    
    for col_name, col_type in columns_to_add_suppliers:
        if col_name not in supplier_columns:
            op.add_column('suppliers', sa.Column(col_name, col_type, nullable=True))
    
    # Check customers table
    customer_columns = [c['name'] for c in inspector.get_columns('customers')]
    
    columns_to_add_customers = [
        ('trade_name', sa.String(255)),
        ('entity_type', sa.String(64)),
        ('tax_id_type', sa.String(32)),
        ('tax_id_country', sa.String(32)),
        ('country', sa.String(64)),
        ('country_incorporation', sa.String(64)),
        ('country_operation', sa.String(64)),
        ('country_residence', sa.String(64)),
        ('base_currency', sa.String(8)),
        ('payment_terms', sa.String(128)),
        ('risk_rating', sa.String(64)),
        ('sanctions_flag', sa.Boolean()),
        ('internal_notes', sa.Text()),
    ]
    
    for col_name, col_type in columns_to_add_customers:
        if col_name not in customer_columns:
            op.add_column('customers', sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    # Remove columns from suppliers
    columns_to_remove = [
        'trade_name', 'entity_type', 'tax_id_type', 'tax_id_country', 'country',
        'country_incorporation', 'country_operation', 'country_residence',
        'base_currency', 'payment_terms', 'risk_rating', 'sanctions_flag', 'internal_notes'
    ]
    
    for col_name in columns_to_remove:
        try:
            op.drop_column('suppliers', col_name)
        except Exception:
            pass
        try:
            op.drop_column('customers', col_name)
        except Exception:
            pass

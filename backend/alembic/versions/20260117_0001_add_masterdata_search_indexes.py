"""add masterdata search indexes

Revision ID: 20260117_0001_add_masterdata_search_indexes
Revises: 20260115_0002_add_fx_policy_map
Create Date: 2026-01-17
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260117_0001_add_masterdata_search_indexes"
down_revision = "20260115_0002_add_fx_policy_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Customers
    op.create_index("ix_customers_tax_id", "customers", ["tax_id"], unique=False)
    op.create_index("ix_customers_contact_email", "customers", ["contact_email"], unique=False)
    op.create_index("ix_customers_contact_phone", "customers", ["contact_phone"], unique=False)
    op.create_index("ix_customers_active", "customers", ["active"], unique=False)

    # Suppliers
    op.create_index("ix_suppliers_tax_id", "suppliers", ["tax_id"], unique=False)
    op.create_index("ix_suppliers_contact_email", "suppliers", ["contact_email"], unique=False)
    op.create_index("ix_suppliers_contact_phone", "suppliers", ["contact_phone"], unique=False)
    op.create_index("ix_suppliers_active", "suppliers", ["active"], unique=False)

    # Counterparties
    op.create_index("ix_counterparties_tax_id", "counterparties", ["tax_id"], unique=False)
    op.create_index(
        "ix_counterparties_contact_email", "counterparties", ["contact_email"], unique=False
    )
    op.create_index(
        "ix_counterparties_contact_phone", "counterparties", ["contact_phone"], unique=False
    )
    op.create_index("ix_counterparties_active", "counterparties", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_counterparties_active", table_name="counterparties")
    op.drop_index("ix_counterparties_contact_phone", table_name="counterparties")
    op.drop_index("ix_counterparties_contact_email", table_name="counterparties")
    op.drop_index("ix_counterparties_tax_id", table_name="counterparties")

    op.drop_index("ix_suppliers_active", table_name="suppliers")
    op.drop_index("ix_suppliers_contact_phone", table_name="suppliers")
    op.drop_index("ix_suppliers_contact_email", table_name="suppliers")
    op.drop_index("ix_suppliers_tax_id", table_name="suppliers")

    op.drop_index("ix_customers_active", table_name="customers")
    op.drop_index("ix_customers_contact_phone", table_name="customers")
    op.drop_index("ix_customers_contact_email", table_name="customers")
    op.drop_index("ix_customers_tax_id", table_name="customers")

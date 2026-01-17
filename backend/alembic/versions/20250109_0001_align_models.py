"""align models with frontend spec

Revision ID: 20250109_0001
Revises: 20231221_0012
Create Date: 2025-01-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20250109_0001_align_models"
down_revision = "20231221_0012_locations_and_costs"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name

    # Drop legacy tables if they exist to simplify alignment
    for table in [
        "hedges",
        "rfq_quotes",
        "rfqs",
        "purchase_orders",
        "sales_orders",
        "suppliers",
        "customers",
        "counterparties",
        "warehouse_locations",
        "users",
        "roles",
    ]:
        if dialect == "postgresql":
            op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        else:
            op.execute(f'DROP TABLE IF EXISTS "{table}"')

    # Drop enums if they exist; use VARCHAR columns instead to avoid enum conflicts
    if dialect == "postgresql":
        for enum_name in [
            "pricingtype",
            "orderstatus",
            "rolename",
            "counterpartytype",
            "rfqstatus",
            "hedgestatus",
        ]:
            op.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE;")

    role_name_enum = sa.String(length=32)
    order_status_enum = sa.String(length=32)
    pricing_type_enum = sa.String(length=32)
    counterparty_type_enum = sa.String(length=32)
    rfq_status_enum = sa.String(length=32)
    hedge_status_enum = sa.String(length=32)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", role_name_enum, nullable=False, unique=True),
        sa.Column("description", sa.String(length=255)),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("code", sa.String(length=32), unique=True),
        sa.Column("contact_email", sa.String(length=255)),
        sa.Column("contact_phone", sa.String(length=64)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("code", sa.String(length=32), unique=True),
        sa.Column("contact_email", sa.String(length=255)),
        sa.Column("contact_phone", sa.String(length=64)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("type", sa.String(length=64)),
        sa.Column("current_stock_mt", sa.Float()),
        sa.Column("capacity_mt", sa.Float()),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("po_number", sa.String(length=50), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("total_quantity_mt", sa.Float(), nullable=False),
        sa.Column("pricing_type", pricing_type_enum, nullable=False, server_default="monthly_average"),
        sa.Column("lme_premium", sa.Float(), server_default="0"),
        sa.Column("status", order_status_enum, nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("so_number", sa.String(length=50), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("total_quantity_mt", sa.Float(), nullable=False),
        sa.Column("pricing_type", pricing_type_enum, nullable=False, server_default="monthly_average"),
        sa.Column("lme_premium", sa.Float(), server_default="0"),
        sa.Column("status", order_status_enum, nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "counterparties",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("type", counterparty_type_enum, nullable=False),
        sa.Column("contact_name", sa.String(length=255)),
        sa.Column("contact_email", sa.String(length=255)),
        sa.Column("contact_phone", sa.String(length=64)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "rfqs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_number", sa.String(length=50), nullable=False, unique=True),
        sa.Column("so_id", sa.Integer(), sa.ForeignKey("sales_orders.id"), nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("status", rfq_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "rfq_quotes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id"), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), sa.ForeignKey("counterparties.id")),
        sa.Column("counterparty_name", sa.String(length=255)),
        sa.Column("quote_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="quoted", nullable=False),
        sa.Column("quoted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hedges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("so_id", sa.Integer(), sa.ForeignKey("sales_orders.id"), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), sa.ForeignKey("counterparties.id"), nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column("contract_price", sa.Float(), nullable=False),
        sa.Column("current_market_price", sa.Float()),
        sa.Column("mtm_value", sa.Float()),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("status", hedge_status_enum, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    dialect = op.get_bind().dialect.name

    for table in [
        "hedges",
        "rfq_quotes",
        "rfqs",
        "counterparties",
        "sales_orders",
        "purchase_orders",
        "warehouse_locations",
        "customers",
        "suppliers",
        "users",
        "roles",
    ]:
        if dialect == "postgresql":
            op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        else:
            op.execute(f'DROP TABLE IF EXISTS "{table}"')

    if dialect == "postgresql":
        for enum_name in [
            "hedgestatus",
            "rfqstatus",
            "counterpartytype",
            "pricingtype",
            "orderstatus",
            "rolename",
        ]:
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")

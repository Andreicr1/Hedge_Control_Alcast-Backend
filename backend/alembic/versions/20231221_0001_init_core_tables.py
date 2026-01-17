"""init core tables

Revision ID: 20231221_0001
Revises: None
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0001_init_core_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    def _enum(*values: str, name: str) -> sa.Enum:
        # SQLite doesn't support ALTER TYPE; avoid CHECK constraints so later enum expansions
        # don't require complex table rebuilds in local dev.
        if is_postgres:
            return sa.Enum(*values, name=name)
        return sa.Enum(*values, name=name, native_enum=False, create_constraint=False)

    role_enum = _enum("admin", "compras", "vendas", "financeiro", name="rolename")
    order_status_enum = _enum("draft", "submitted", "hedged", "settled", name="orderstatus")
    hedge_status_enum = _enum("planned", "rfq", "executed", "closed", name="hedgestatus")
    hedge_type_enum = _enum("purchase", "sale", name="hedgetype")
    hedge_side_enum = _enum("buy", "sell", name="hedgeside")
    rfq_status_enum = _enum("draft", "sent", "quoted", "awarded", "expired", name="rfqstatus")
    rfq_type_enum = _enum("hedge_buy", "hedge_sell", name="rfqtype")
    market_obj_enum = _enum("hedge", "po", "so", "portfolio", name="marketobjecttype")

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", role_enum, nullable=False, unique=True),
        sa.Column("description", sa.String(length=255)),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("country", sa.String(length=64)),
        sa.Column("contact", sa.String(length=255)),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("country", sa.String(length=64)),
        sa.Column("contact", sa.String(length=255)),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("quantity_tons", sa.Float(), nullable=False),
        sa.Column("aluminum_type", sa.String(length=120), nullable=False),
        sa.Column("expected_delivery_date", sa.Date()),
        sa.Column("expected_payment_date", sa.Date()),
        sa.Column("payment_terms", sa.String(length=255)),
        sa.Column("currency", sa.String(length=8), server_default="USD"),
        sa.Column("notes", sa.Text()),
        sa.Column("status", order_status_enum, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("quantity_tons", sa.Float(), nullable=False),
        sa.Column("aluminum_type", sa.String(length=120), nullable=False),
        sa.Column("expected_delivery_date", sa.Date()),
        sa.Column("expected_receipt_date", sa.Date()),
        sa.Column("receipt_terms", sa.String(length=255)),
        sa.Column("currency", sa.String(length=8), server_default="USD"),
        sa.Column("notes", sa.Text()),
        sa.Column("status", order_status_enum, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "so_po_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sales_order_id", sa.Integer(), sa.ForeignKey("sales_orders.id"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("link_ratio", sa.Float()),
        sa.UniqueConstraint("sales_order_id", "purchase_order_id", name="uq_so_po"),
    )

    op.create_table(
        "rfqs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_type", rfq_type_enum, nullable=False),
        sa.Column("reference_po_id", sa.Integer(), sa.ForeignKey("purchase_orders.id")),
        sa.Column("reference_so_id", sa.Integer(), sa.ForeignKey("sales_orders.id")),
        sa.Column("tenor_month", sa.String(length=16)),
        sa.Column("quantity_tons", sa.Float(), nullable=False),
        sa.Column("channel", sa.String(length=32), server_default="api"),
        sa.Column("status", rfq_status_enum, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "hedge_trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hedge_type", hedge_type_enum, nullable=False),
        sa.Column("side", hedge_side_enum, nullable=False),
        sa.Column("lme_contract", sa.String(length=32), nullable=False),
        sa.Column("contract_month", sa.String(length=16), nullable=False),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("lots", sa.Integer(), nullable=False),
        sa.Column("lot_size_tons", sa.Float(), server_default=sa.text("25.0")),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD"),
        sa.Column("notional_tons", sa.Float(), nullable=False),
        sa.Column("status", hedge_status_enum, server_default="planned"),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id")),
        sa.Column("sales_order_id", sa.Integer(), sa.ForeignKey("sales_orders.id")),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id")),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rfq_quotes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id"), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fee_bps", sa.Float()),
        sa.Column("currency", sa.String(length=8), server_default="USD"),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("ranking_score", sa.Float()),
        sa.Column("selected", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "market_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("contract_month", sa.String(length=16)),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "symbol", "contract_month", "as_of", name="uq_market_price"),
    )

    op.create_table(
        "mtm_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("object_type", market_obj_enum, nullable=False),
        sa.Column("object_id", sa.Integer()),
        sa.Column("forward_price", sa.Float()),
        sa.Column("fx_rate", sa.Float()),
        sa.Column("mtm_value", sa.Float(), nullable=False),
        sa.Column("methodology", sa.String(length=255)),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("mtm_records")
    op.drop_table("market_prices")
    op.drop_table("rfq_quotes")
    op.drop_table("hedge_trades")
    op.drop_table("rfqs")
    op.drop_table("so_po_links")
    op.drop_table("sales_orders")
    op.drop_table("purchase_orders")
    op.drop_table("customers")
    op.drop_table("suppliers")
    op.drop_table("users")
    op.drop_table("roles")

    op.execute("DROP TYPE IF EXISTS marketobjecttype")
    op.execute("DROP TYPE IF EXISTS rfqtype")
    op.execute("DROP TYPE IF EXISTS rfqstatus")
    op.execute("DROP TYPE IF EXISTS hedgeside")
    op.execute("DROP TYPE IF EXISTS hedgetype")
    op.execute("DROP TYPE IF EXISTS hedgestatus")
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS rolename")

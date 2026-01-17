"""add warehouse locations and cost fields

Revision ID: 20231221_0012
Revises: 20231221_0011
Create Date: 2024-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20231221_0012_locations_and_costs"
down_revision = "20231221_0011_add_counterparties"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("purchase_orders", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("purchase_orders", sa.Column("avg_cost", sa.Float(), nullable=True))
    op.add_column("purchase_orders", sa.Column("arrival_date", sa.Date(), nullable=True))
    op.add_column("sales_orders", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("counterparties", sa.Column("send_instructions", sa.Text(), nullable=True))

    # SQLite cannot ALTER TABLE to add foreign keys; keep dev DB functional without them.
    if not is_sqlite:
        op.create_foreign_key(
            "fk_purchase_orders_location",
            "purchase_orders",
            "warehouse_locations",
            ["location_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_sales_orders_location",
            "sales_orders",
            "warehouse_locations",
            ["location_id"],
            ["id"],
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_sales_orders_location", "sales_orders", type_="foreignkey")
        op.drop_constraint("fk_purchase_orders_location", "purchase_orders", type_="foreignkey")
    op.drop_column("counterparties", "send_instructions")
    op.drop_column("sales_orders", "location_id")
    op.drop_column("purchase_orders", "arrival_date")
    op.drop_column("purchase_orders", "avg_cost")
    op.drop_column("purchase_orders", "location_id")
    op.drop_table("warehouse_locations")

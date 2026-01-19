"""add lme_prices

Revision ID: 20260118_0003_add_lme_prices
Revises: 20260118_0002_add_rfq_sent_awarded_at
Create Date: 2026-01-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260118_0003_add_lme_prices"
down_revision = "20260118_0002_add_rfq_sent_awarded_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    id_col = sa.Column("id", sa.String(length=36), primary_key=True)
    id_server_default = None

    # On Postgres/Supabase, prefer server-side UUID generation.
    if dialect == "postgresql":
        try:
            id_col = sa.Column("id", sa.Uuid(), primary_key=True)
            id_server_default = sa.text("gen_random_uuid()")
        except Exception:
            id_col = sa.Column("id", sa.String(length=36), primary_key=True)

    if id_server_default is not None:
        id_col.server_default = id_server_default

    op.create_table(
        "lme_prices",
        id_col,
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "price_type",
            sa.String(length=16),
            sa.CheckConstraint("price_type in ('live','official')", name="ck_lme_prices_price_type"),
            nullable=False,
        ),
        sa.Column("ts_price", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_ingest", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source", sa.String(length=64), nullable=False),
    )

    op.create_index(
        "idx_lme_prices_symbol_ts",
        "lme_prices",
        ["symbol", "ts_price"],
    )
    op.create_index("ix_lme_prices_price_type", "lme_prices", ["price_type"])


def downgrade() -> None:
    op.drop_index("ix_lme_prices_price_type", table_name="lme_prices")
    op.drop_index("idx_lme_prices_symbol_ts", table_name="lme_prices")
    op.drop_table("lme_prices")

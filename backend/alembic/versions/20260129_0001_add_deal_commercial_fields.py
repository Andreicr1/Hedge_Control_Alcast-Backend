"""add deal commercial fields

Revision ID: 20260129_0001_add_deal_commercial_fields
Revises: 20260121_0004_add_lme_prices_ts_price_index
Create Date: 2026-01-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260129_0001_add_deal_commercial_fields"
down_revision = "20260121_0004_add_lme_prices_ts_price_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # We keep these as VARCHAR columns (native_enum=False in models) to stay compatible
    # with Supabase schemas and SQLite dev DBs.
    with op.batch_alter_table("deals") as batch:
        batch.add_column(sa.Column("company", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("economic_period", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column(
                "commercial_status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            )
        )

    # Indexes (IF NOT EXISTS to be idempotent across environments)
    if dialect == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_deals_company ON public.deals (company)")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_deals_economic_period ON public.deals (economic_period)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_deals_commercial_status ON public.deals (commercial_status)"
        )
    else:
        op.create_index("ix_deals_company", "deals", ["company"], unique=False)
        op.create_index("ix_deals_economic_period", "deals", ["economic_period"], unique=False)
        op.create_index("ix_deals_commercial_status", "deals", ["commercial_status"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS public.ix_deals_commercial_status")
        op.execute("DROP INDEX IF EXISTS public.ix_deals_economic_period")
        op.execute("DROP INDEX IF EXISTS public.ix_deals_company")
    else:
        op.drop_index("ix_deals_commercial_status", table_name="deals")
        op.drop_index("ix_deals_economic_period", table_name="deals")
        op.drop_index("ix_deals_company", table_name="deals")

    with op.batch_alter_table("deals") as batch:
        batch.drop_column("commercial_status")
        batch.drop_column("economic_period")
        batch.drop_column("company")

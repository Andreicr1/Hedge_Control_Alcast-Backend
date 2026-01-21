"""add market price indexes

Revision ID: 20260120_0004_add_market_price_indexes
Revises: 20260120_0003_fix_finance_risk_flag_created_at
Create Date: 2026-01-20
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260120_0004_add_market_price_indexes"
down_revision = "20260120_0003_fix_finance_risk_flag_created_at"
branch_labels = None
depends_on = None


INDEX_LME = "ix_lme_prices_symbol_price_type_ts"
INDEX_MARKET = "ix_market_prices_symbol"


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            f"{INDEX_LME} ON public.lme_prices (symbol, price_type, ts_price)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            f"{INDEX_MARKET} ON public.market_prices (symbol)"
        )


def downgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{INDEX_MARKET}")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{INDEX_LME}")

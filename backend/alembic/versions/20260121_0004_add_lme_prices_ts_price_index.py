"""add lme_prices ts_price index

Revision ID: 20260121_0004_add_lme_prices_ts_price_index
Revises: 20260121_0003_add_contracts_created_at_index
Create Date: 2026-01-21
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260121_0004_add_lme_prices_ts_price_index"
down_revision = "20260121_0003_add_contracts_created_at_index"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_lme_prices_ts_price"


def upgrade() -> None:
    op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON public.lme_prices (ts_price)")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS public.{INDEX_NAME}")

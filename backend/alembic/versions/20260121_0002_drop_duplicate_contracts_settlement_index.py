"""drop duplicate contracts settlement index

Revision ID: 20260121_0002_drop_duplicate_contracts_settlement_index
Revises: 20260121_0001_add_fk_covering_indexes
Create Date: 2026-01-21
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260121_0002_drop_duplicate_contracts_settlement_index"
down_revision = "20260121_0001_add_fk_covering_indexes"
branch_labels = None
depends_on = None


DUPLICATE_INDEX = "idx_contracts_settlement_date"
KEEP_INDEX = "ix_contracts_settlement_date"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS public.{DUPLICATE_INDEX}")


def downgrade() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {DUPLICATE_INDEX} ON public.contracts (settlement_date)"
    )

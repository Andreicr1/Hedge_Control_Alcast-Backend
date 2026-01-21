"""add contracts created_at index

Revision ID: 20260121_0003_add_contracts_created_at_index
Revises: 20260121_0002_drop_duplicate_contracts_settlement_index
Create Date: 2026-01-21
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260121_0003_add_contracts_created_at_index"
down_revision = "20260121_0002_drop_duplicate_contracts_settlement_index"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_contracts_created_at"


def upgrade() -> None:
    op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON public.contracts (created_at)")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS public.{INDEX_NAME}")

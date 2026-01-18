"""add partially_hedged to postgres enums

Revision ID: 20260118_0001_add_partially_hedged_to_enums
Revises: 20260117_0006_add_contract_exposures
Create Date: 2026-01-18
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260118_0001_add_partially_hedged_to_enums"
down_revision = "20260117_0006_add_contract_exposures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
DO $$
BEGIN
  -- exposurestatus
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'exposurestatus') THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      WHERE t.typname = 'exposurestatus'
        AND e.enumlabel = 'partially_hedged'
    ) THEN
      ALTER TYPE exposurestatus ADD VALUE 'partially_hedged';
    END IF;
  END IF;

  -- deallifecyclestatus
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'deallifecyclestatus') THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      WHERE t.typname = 'deallifecyclestatus'
        AND e.enumlabel = 'partially_hedged'
    ) THEN
      ALTER TYPE deallifecyclestatus ADD VALUE 'partially_hedged';
    END IF;
  END IF;
END $$;
        """
    )


def downgrade() -> None:
    # Postgres does not support dropping enum labels safely.
    pass

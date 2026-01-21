"""fix cashflow baseline created_at defaults

Revision ID: 20260120_0002_fix_cashflow_baseline_created_at
Revises: 20260120_0001_add_perf_indexes
Create Date: 2026-01-20
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260120_0002_fix_cashflow_baseline_created_at"
down_revision = "20260120_0001_add_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cashflow_baseline_runs",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "cashflow_baseline_items",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "cashflow_baseline_items",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "cashflow_baseline_runs",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
"""fix finance risk flag created_at defaults

Revision ID: 20260120_0003_fix_finance_risk_flag_created_at
Revises: 20260120_0002_fix_cashflow_baseline_created_at
Create Date: 2026-01-20
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260120_0003_fix_finance_risk_flag_created_at"
down_revision = "20260120_0002_fix_cashflow_baseline_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "finance_risk_flag_runs",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "finance_risk_flags",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "finance_risk_flags",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "finance_risk_flag_runs",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
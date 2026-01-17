"""add finance pipeline step artifacts (phase 6.3.5)

Revision ID: 20260114_0002_add_finance_pipeline_step_artifacts
Revises: 20260114_0001_add_finance_pipeline_runs
Create Date: 2026-01-14
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260114_0002_add_finance_pipeline_step_artifacts"
down_revision = "20260114_0001_add_finance_pipeline_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "finance_pipeline_steps",
        sa.Column("artifacts", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("finance_pipeline_steps", "artifacts")

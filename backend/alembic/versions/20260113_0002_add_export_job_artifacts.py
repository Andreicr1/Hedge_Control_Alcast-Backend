"""add export job artifacts

Revision ID: 20260113_0002_add_export_job_artifacts
Revises: 20260113_0001_add_export_jobs
Create Date: 2026-01-13
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260113_0002_add_export_job_artifacts"
down_revision = "20260113_0001_add_export_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_jobs", sa.Column("artifacts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_jobs", "artifacts")

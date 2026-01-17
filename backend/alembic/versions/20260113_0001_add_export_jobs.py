"""add export jobs

Revision ID: 20260113_0001_add_export_jobs
Revises: 20260112_0004_add_timeline_events
Create Date: 2026-01-13
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260113_0001_add_export_jobs"
down_revision = "20260112_0004_add_timeline_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_id", sa.String(length=40), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("export_id", name="uq_export_jobs_export_id"),
    )

    op.create_index("ix_export_jobs_export_id", "export_jobs", ["export_id"])
    op.create_index("ix_export_jobs_inputs_hash", "export_jobs", ["inputs_hash"])
    op.create_index("ix_export_jobs_export_type", "export_jobs", ["export_type"])
    op.create_index("ix_export_jobs_as_of", "export_jobs", ["as_of"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.create_index(
        "ix_export_jobs_requested_by_user_id",
        "export_jobs",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_requested_by_user_id", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_as_of", table_name="export_jobs")
    op.drop_index("ix_export_jobs_export_type", table_name="export_jobs")
    op.drop_index("ix_export_jobs_inputs_hash", table_name="export_jobs")
    op.drop_index("ix_export_jobs_export_id", table_name="export_jobs")
    op.drop_constraint("uq_export_jobs_export_id", "export_jobs", type_="unique")
    op.drop_table("export_jobs")

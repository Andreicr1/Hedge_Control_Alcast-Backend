"""add finance pipeline runs + steps (phase 6.3.1)

Revision ID: 20260114_0001_add_finance_pipeline_runs
Revises: 20260113_0003_add_pnl_read_models
Create Date: 2026-01-14
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260114_0001_add_finance_pipeline_runs"
down_revision = "20260113_0003_add_pnl_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.create_table(
        "finance_pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pipeline_version", sa.String(length=128), nullable=False, index=True),
        sa.Column("as_of_date", sa.Date(), nullable=False, index=True),
        sa.Column("scope_filters", sa.JSON(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="materialize"),
        sa.Column("emit_exports", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued", index=True),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_finance_pipeline_runs_inputs_hash", "finance_pipeline_runs", ["inputs_hash"])
    if dialect == "sqlite":
        op.create_index(
            "uq_finance_pipeline_runs_inputs_hash",
            "finance_pipeline_runs",
            ["inputs_hash"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_finance_pipeline_runs_inputs_hash",
            "finance_pipeline_runs",
            ["inputs_hash"],
        )
    op.create_index(
        "ix_finance_pipeline_runs_requested_by_user_id",
        "finance_pipeline_runs",
        ["requested_by_user_id"],
    )

    op.create_table(
        "finance_pipeline_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("finance_pipeline_runs.id"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_finance_pipeline_steps_run_id", "finance_pipeline_steps", ["run_id"])
    op.create_index("ix_finance_pipeline_steps_step_name", "finance_pipeline_steps", ["step_name"])
    if dialect == "sqlite":
        op.create_index(
            "uq_finance_pipeline_steps_run_step",
            "finance_pipeline_steps",
            ["run_id", "step_name"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_finance_pipeline_steps_run_step",
            "finance_pipeline_steps",
            ["run_id", "step_name"],
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        op.drop_index("uq_finance_pipeline_steps_run_step", table_name="finance_pipeline_steps")
    else:
        op.drop_constraint(
            "uq_finance_pipeline_steps_run_step",
            "finance_pipeline_steps",
            type_="unique",
        )
    op.drop_index("ix_finance_pipeline_steps_step_name", table_name="finance_pipeline_steps")
    op.drop_index("ix_finance_pipeline_steps_run_id", table_name="finance_pipeline_steps")
    op.drop_table("finance_pipeline_steps")

    op.drop_index("ix_finance_pipeline_runs_requested_by_user_id", table_name="finance_pipeline_runs")
    if dialect == "sqlite":
        op.drop_index("uq_finance_pipeline_runs_inputs_hash", table_name="finance_pipeline_runs")
    else:
        op.drop_constraint(
            "uq_finance_pipeline_runs_inputs_hash",
            "finance_pipeline_runs",
            type_="unique",
        )
    op.drop_index("ix_finance_pipeline_runs_inputs_hash", table_name="finance_pipeline_runs")
    op.drop_table("finance_pipeline_runs")

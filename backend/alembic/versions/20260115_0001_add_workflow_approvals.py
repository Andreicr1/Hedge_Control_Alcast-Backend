"""add workflow approvals (requests + decisions) and audit idempotency

Revision ID: 20260115_0001_add_workflow_approvals
Revises: 20260114_0004_add_cashflow_baseline_and_risk_flags
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260115_0001_add_workflow_approvals"
down_revision = "20260114_0004_add_cashflow_baseline_and_risk_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit idempotency (nullable; idempotent emitters opt-in)
    op.add_column(
        "audit_logs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_audit_logs_idempotency_key",
        "audit_logs",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "workflow_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_key", sa.String(length=40), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False, index=True),
        sa.Column("subject_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("subject_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
        sa.Column("notional_usd", sa.Float(), nullable=True),
        sa.Column("threshold_usd", sa.Float(), nullable=True),
        sa.Column("required_role", sa.String(length=32), nullable=False, index=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("request_key", name="uq_workflow_requests_request_key"),
        sa.UniqueConstraint("inputs_hash", name="uq_workflow_requests_inputs_hash"),
    )

    op.create_table(
        "workflow_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_request_id", sa.Integer(), sa.ForeignKey("workflow_requests.id"), nullable=False, index=True),
        sa.Column("decision", sa.String(length=16), nullable=False, index=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_decisions_idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("workflow_decisions")
    op.drop_table("workflow_requests")

    op.drop_index("ix_audit_logs_idempotency_key", table_name="audit_logs")
    op.drop_column("audit_logs", "idempotency_key")

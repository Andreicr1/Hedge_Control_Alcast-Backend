"""Add request context columns to audit_logs

Revision ID: 20260112_0001_add_audit_request_context
Revises: 20260111_0005_counterparty_remaining_columns
Create Date: 2026-01-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260112_0001_add_audit_request_context"
down_revision = "20260111_0005_counterparty_remaining_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("audit_logs")}

    if "request_id" not in cols:
        op.add_column("audit_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
        op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])

    if "ip" not in cols:
        op.add_column("audit_logs", sa.Column("ip", sa.String(length=64), nullable=True))

    if "user_agent" not in cols:
        op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=256), nullable=True))


def downgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("audit_logs")}

    # Index and columns might not exist depending on environment state.
    try:
        op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    except Exception:
        pass

    if "user_agent" in cols:
        op.drop_column("audit_logs", "user_agent")
    if "ip" in cols:
        op.drop_column("audit_logs", "ip")
    if "request_id" in cols:
        op.drop_column("audit_logs", "request_id")

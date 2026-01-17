"""add timeline events

Revision ID: 20260112_0004_add_timeline_events
Revises: 20260112_0003_add_counterparty_kyc_checks
Create Date: 2026-01-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260112_0004_add_timeline_events"
down_revision = "20260112_0003_add_counterparty_kyc_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("supersedes_event_id", sa.Integer(), sa.ForeignKey("timeline_events.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("audit_log_id", sa.Integer(), sa.ForeignKey("audit_logs.id"), nullable=True),
        sa.Column("visibility", sa.String(length=16), server_default="all", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_timeline_events_event_type", "timeline_events", ["event_type"])
    op.create_index("ix_timeline_events_occurred_at", "timeline_events", ["occurred_at"])
    op.create_index("ix_timeline_events_subject_type", "timeline_events", ["subject_type"])
    op.create_index("ix_timeline_events_subject_id", "timeline_events", ["subject_id"])
    op.create_index("ix_timeline_events_correlation_id", "timeline_events", ["correlation_id"])
    op.create_index("ix_timeline_events_supersedes_event_id", "timeline_events", ["supersedes_event_id"])
    op.create_index("ix_timeline_events_actor_user_id", "timeline_events", ["actor_user_id"])
    op.create_index("ix_timeline_events_audit_log_id", "timeline_events", ["audit_log_id"])
    op.create_index("ix_timeline_events_visibility", "timeline_events", ["visibility"])

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.create_index(
            "uq_timeline_events_event_type_idempotency_key",
            "timeline_events",
            ["event_type", "idempotency_key"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_timeline_events_event_type_idempotency_key",
            "timeline_events",
            ["event_type", "idempotency_key"],
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.drop_index("uq_timeline_events_event_type_idempotency_key", table_name="timeline_events")
    else:
        op.drop_constraint("uq_timeline_events_event_type_idempotency_key", "timeline_events", type_="unique")
    op.drop_index("ix_timeline_events_visibility", table_name="timeline_events")
    op.drop_index("ix_timeline_events_audit_log_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_actor_user_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_supersedes_event_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_correlation_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_subject_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_subject_type", table_name="timeline_events")
    op.drop_index("ix_timeline_events_occurred_at", table_name="timeline_events")
    op.drop_index("ix_timeline_events_event_type", table_name="timeline_events")
    op.drop_table("timeline_events")

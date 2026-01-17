"""add rfq send attempts

Revision ID: 20231221_0005
Revises: 20231221_0004
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20231221_0005_rfq_send_attempts"
down_revision = "20231221_0004_add_rfq_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Create enum idempotently (IF NOT EXISTS) to avoid duplicate-object errors
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sendstatus') THEN
                    CREATE TYPE sendstatus AS ENUM ('queued', 'sent', 'delivered', 'read', 'failed');
                END IF;
            END$$;
            """
        )
        send_status_enum = postgresql.ENUM(
            "queued",
            "sent",
            "delivered",
            "read",
            "failed",
            name="sendstatus",
            create_type=False,  # type already created by DO block above
        )
    else:
        # SQLite (and others): emulate enum using CHECK constraint.
        send_status_enum = sa.Enum(
            "queued",
            "sent",
            "delivered",
            "read",
            "failed",
            name="sendstatus",
        )

    op.create_table(
        "rfq_send_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id"), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", send_status_enum, nullable=False, server_default="queued"),
        sa.Column("provider_message_id", sa.String(length=128)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("rfq_send_attempts")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS sendstatus")

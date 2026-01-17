"""add mtm snapshots and extend marketobjecttype

Revision ID: 20250110_0006
Revises: 20250110_0005
Create Date: 2025-01-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


revision = "20250110_0006_mtm_snapshots"
down_revision = "20250110_0005_hedge_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Ensure enum exists and contains new labels (exposure, net)
    if dialect == "postgresql":
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'marketobjecttype') THEN
                        CREATE TYPE marketobjecttype AS ENUM ('hedge', 'po', 'so', 'portfolio', 'exposure', 'net');
                    END IF;
                END$$;
                """
            )
        )
        # add missing enum values (safe if already present)
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum e
                        JOIN pg_type t ON e.enumtypid = t.oid
                        WHERE t.typname = 'marketobjecttype' AND e.enumlabel = 'exposure'
                    ) THEN
                        ALTER TYPE marketobjecttype ADD VALUE 'exposure';
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum e
                        JOIN pg_type t ON e.enumtypid = t.oid
                        WHERE t.typname = 'marketobjecttype' AND e.enumlabel = 'net'
                    ) THEN
                        ALTER TYPE marketobjecttype ADD VALUE 'net';
                    END IF;
                END$$;
                """
            )
        )
        market_object_enum = postgresql.ENUM(
            "hedge",
            "po",
            "so",
            "portfolio",
            "exposure",
            "net",
            name="marketobjecttype",
            create_type=False,
        )
    else:
        market_object_enum = sa.String(length=32)

    op.create_table(
        "mtm_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("object_type", market_object_enum, nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("period", sa.String(length=32), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column("mtm_value", sa.Float(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_mtm_snapshots_object", "object_type", "object_id"),
    )


def downgrade() -> None:
    op.drop_table("mtm_snapshots")
    # Do not drop marketobjecttype to avoid impacting earlier migrations/data

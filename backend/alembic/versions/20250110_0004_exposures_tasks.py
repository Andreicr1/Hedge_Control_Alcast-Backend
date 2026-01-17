"""add exposures and hedge tasks

Revision ID: 20250110_0004
Revises: 20250110_0003
Create Date: 2025-01-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20250110_0004_exposures_tasks"
down_revision = "20250110_0003_po_so_fields_mtm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "postgresql":
        # ensure enums exist (idempotent)
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'exposuretype') THEN
                    CREATE TYPE exposuretype AS ENUM ('active', 'passive');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'exposurestatus') THEN
                    CREATE TYPE exposurestatus AS ENUM ('open', 'hedged', 'closed');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hedgetaskstatus') THEN
                    CREATE TYPE hedgetaskstatus AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'marketobjecttype') THEN
                    CREATE TYPE marketobjecttype AS ENUM ('hedge', 'po', 'so', 'portfolio');
                END IF;
            END$$;
            """
        )

        exposure_type_enum = postgresql.ENUM("active", "passive", name="exposuretype", create_type=False)
        exposure_status_enum = postgresql.ENUM("open", "hedged", "closed", name="exposurestatus", create_type=False)
        task_status_enum = postgresql.ENUM(
            "pending",
            "in_progress",
            "completed",
            "cancelled",
            name="hedgetaskstatus",
            create_type=False,
        )
        market_object_enum = postgresql.ENUM(
            "hedge",
            "po",
            "so",
            "portfolio",
            name="marketobjecttype",
            create_type=False,
        )
    else:
        # SQLite (and others): use VARCHAR to avoid enum DDL.
        exposure_type_enum = sa.String(length=32)
        exposure_status_enum = sa.String(length=32)
        task_status_enum = sa.String(length=32)
        market_object_enum = sa.String(length=32)

    op.create_table(
        "exposures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_type", market_object_enum, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("exposure_type", exposure_type_enum, nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("sale_date", sa.Date(), nullable=True),
        sa.Column("status", exposure_status_enum, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_exposures_source", "source_type", "source_id"),
    )

    op.create_table(
        "hedge_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exposure_id", sa.Integer(), sa.ForeignKey("exposures.id"), nullable=False),
        sa.Column("status", task_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.drop_table("hedge_tasks")
    op.drop_table("exposures")

    if dialect == "postgresql":
        task_status_enum = sa.Enum("pending", "in_progress", "completed", "cancelled", name="hedgetaskstatus")
        exposure_status_enum = sa.Enum("open", "hedged", "closed", name="exposurestatus")
        exposure_type_enum = sa.Enum("active", "passive", name="exposuretype")
        task_status_enum.drop(op.get_bind(), checkfirst=True)
        exposure_status_enum.drop(op.get_bind(), checkfirst=True)
        exposure_type_enum.drop(op.get_bind(), checkfirst=True)

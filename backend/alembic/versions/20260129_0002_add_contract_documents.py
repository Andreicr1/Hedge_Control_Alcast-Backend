"""add contract documents

Revision ID: 20260129_0002_add_contract_documents
Revises: 20260129_0001_add_deal_commercial_fields
Create Date: 2026-01-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260129_0002_add_contract_documents"
down_revision = "20260129_0001_add_deal_commercial_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.create_table(
        "contract_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(length=36), sa.ForeignKey("contracts.contract_id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("contract_id", "version", name="uq_contract_documents_contract_version"),
    )

    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_contract_documents_contract_id ON public.contract_documents (contract_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_contract_documents_uploaded_at ON public.contract_documents (uploaded_at)"
        )
    else:
        op.create_index(
            "ix_contract_documents_contract_id",
            "contract_documents",
            ["contract_id"],
            unique=False,
        )
        op.create_index(
            "ix_contract_documents_uploaded_at",
            "contract_documents",
            ["uploaded_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS public.ix_contract_documents_uploaded_at")
        op.execute("DROP INDEX IF EXISTS public.ix_contract_documents_contract_id")
    else:
        op.drop_index("ix_contract_documents_uploaded_at", table_name="contract_documents")
        op.drop_index("ix_contract_documents_contract_id", table_name="contract_documents")

    op.drop_table("contract_documents")

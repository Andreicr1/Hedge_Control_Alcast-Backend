"""add monthly document sequences and contract_number

Revision ID: 20260117_0004_add_document_sequences_and_contract_number
Revises: 20260117_0003_add_deal_reference_name
Create Date: 2026-01-17
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260117_0004_add_document_sequences_and_contract_number"
down_revision = "20260117_0003_add_deal_reference_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_monthly_sequences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("year_month", sa.String(length=6), nullable=False),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "doc_type",
            "year_month",
            name="uq_doc_seq_doc_type_year_month",
        ),
    )
    op.create_index(
        "ix_document_monthly_sequences_doc_type_year_month",
        "document_monthly_sequences",
        ["doc_type", "year_month"],
        unique=False,
    )

    op.add_column("contracts", sa.Column("contract_number", sa.String(length=50), nullable=True))
    op.create_index(
        "ix_contracts_contract_number",
        "contracts",
        ["contract_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_contracts_contract_number", table_name="contracts")
    op.drop_column("contracts", "contract_number")

    op.drop_index(
        "ix_document_monthly_sequences_doc_type_year_month",
        table_name="document_monthly_sequences",
    )
    op.drop_table("document_monthly_sequences")

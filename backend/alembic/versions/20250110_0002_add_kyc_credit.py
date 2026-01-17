"""add kyc fields and credit tables

Revision ID: 20250110_0002
Revises: 20250109_0001
Create Date: 2025-01-10
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250110_0002_add_kyc_credit"
down_revision = "20250109_0001_align_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("suppliers", sa.Column("tax_id", sa.String(length=32), nullable=True))
    op.add_column("suppliers", sa.Column("state_registration", sa.String(length=64), nullable=True))
    op.add_column("suppliers", sa.Column("address_line", sa.String(length=255), nullable=True))
    op.add_column("suppliers", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("suppliers", sa.Column("state", sa.String(length=8), nullable=True))
    op.add_column("suppliers", sa.Column("postal_code", sa.String(length=32), nullable=True))
    op.add_column("suppliers", sa.Column("credit_limit", sa.Float(), nullable=True))
    op.add_column("suppliers", sa.Column("credit_score", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("kyc_status", sa.String(length=32), nullable=True))
    op.add_column("suppliers", sa.Column("kyc_notes", sa.Text(), nullable=True))

    op.add_column("customers", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("customers", sa.Column("tax_id", sa.String(length=32), nullable=True))
    op.add_column("customers", sa.Column("state_registration", sa.String(length=64), nullable=True))
    op.add_column("customers", sa.Column("address_line", sa.String(length=255), nullable=True))
    op.add_column("customers", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("customers", sa.Column("state", sa.String(length=8), nullable=True))
    op.add_column("customers", sa.Column("postal_code", sa.String(length=32), nullable=True))
    op.add_column("customers", sa.Column("credit_limit", sa.Float(), nullable=True))
    op.add_column("customers", sa.Column("credit_score", sa.Integer(), nullable=True))
    op.add_column("customers", sa.Column("kyc_status", sa.String(length=32), nullable=True))
    op.add_column("customers", sa.Column("kyc_notes", sa.Text(), nullable=True))

    op.create_table(
        "kyc_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.Enum("customer", "supplier", name="documentownertype"), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Index("ix_kyc_documents_owner", "owner_id"),
    )

    op.create_table(
        "credit_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.Enum("customer", "supplier", name="documentownertype"), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("bureau", sa.String(length=128), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_credit_checks_owner", "owner_id"),
    )


def downgrade() -> None:
    op.drop_table("credit_checks")
    op.drop_table("kyc_documents")

    op.drop_column("customers", "kyc_notes")
    op.drop_column("customers", "kyc_status")
    op.drop_column("customers", "credit_score")
    op.drop_column("customers", "credit_limit")
    op.drop_column("customers", "postal_code")
    op.drop_column("customers", "state")
    op.drop_column("customers", "city")
    op.drop_column("customers", "address_line")
    op.drop_column("customers", "state_registration")
    op.drop_column("customers", "tax_id")
    op.drop_column("customers", "legal_name")

    op.drop_column("suppliers", "kyc_notes")
    op.drop_column("suppliers", "kyc_status")
    op.drop_column("suppliers", "credit_score")
    op.drop_column("suppliers", "credit_limit")
    op.drop_column("suppliers", "postal_code")
    op.drop_column("suppliers", "state")
    op.drop_column("suppliers", "city")
    op.drop_column("suppliers", "address_line")
    op.drop_column("suppliers", "state_registration")
    op.drop_column("suppliers", "tax_id")
    op.drop_column("suppliers", "legal_name")

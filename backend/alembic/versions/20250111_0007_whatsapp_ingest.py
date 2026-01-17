"""Add RFQ invitation table and whatsapp fields"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250111_0007_whatsapp_ingest"
down_revision = "20250110_0006_mtm_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfq_invitations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), sa.ForeignKey("counterparties.id"), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )

    op.add_column("rfq_quotes", sa.Column("price_type", sa.String(length=128), nullable=True))
    op.add_column("rfq_quotes", sa.Column("volume_mt", sa.Float(), nullable=True))
    op.add_column("rfq_quotes", sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rfq_quotes", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("rfq_quotes", sa.Column("channel", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("rfq_quotes", "channel")
    op.drop_column("rfq_quotes", "notes")
    op.drop_column("rfq_quotes", "valid_until")
    op.drop_column("rfq_quotes", "volume_mt")
    op.drop_column("rfq_quotes", "price_type")
    op.drop_table("rfq_invitations")

"""Add RFQ decision fields and invitation table"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250111_0008_rfq_award"
down_revision = "20250111_0007_whatsapp_ingest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("rfqs") as batch_op:
            batch_op.add_column(sa.Column("winner_quote_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("decision_reason", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("decided_by", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("winner_rank", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("hedge_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("hedge_reference", sa.String(length=128), nullable=True))

            batch_op.create_foreign_key(
                "fk_rfqs_winner_quote_id__rfq_quotes_id",
                "rfq_quotes",
                ["winner_quote_id"],
                ["id"],
            )
            batch_op.create_foreign_key(
                "fk_rfqs_decided_by__users_id",
                "users",
                ["decided_by"],
                ["id"],
            )
            batch_op.create_foreign_key(
                "fk_rfqs_hedge_id__hedges_id",
                "hedges",
                ["hedge_id"],
                ["id"],
            )
    else:
        op.add_column("rfqs", sa.Column("winner_quote_id", sa.Integer(), sa.ForeignKey("rfq_quotes.id"), nullable=True))
        op.add_column("rfqs", sa.Column("decision_reason", sa.Text(), nullable=True))
        op.add_column("rfqs", sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
        op.add_column("rfqs", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("rfqs", sa.Column("winner_rank", sa.Integer(), nullable=True))
        op.add_column("rfqs", sa.Column("hedge_id", sa.Integer(), sa.ForeignKey("hedges.id"), nullable=True))
        op.add_column("rfqs", sa.Column("hedge_reference", sa.String(length=128), nullable=True))


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("rfqs") as batch_op:
            batch_op.drop_constraint("fk_rfqs_hedge_id__hedges_id", type_="foreignkey")
            batch_op.drop_constraint("fk_rfqs_decided_by__users_id", type_="foreignkey")
            batch_op.drop_constraint("fk_rfqs_winner_quote_id__rfq_quotes_id", type_="foreignkey")
            batch_op.drop_column("hedge_reference")
            batch_op.drop_column("hedge_id")
            batch_op.drop_column("winner_rank")
            batch_op.drop_column("decided_at")
            batch_op.drop_column("decided_by")
            batch_op.drop_column("decision_reason")
            batch_op.drop_column("winner_quote_id")
    else:
        op.drop_column("rfqs", "hedge_reference")
        op.drop_column("rfqs", "hedge_id")
        op.drop_column("rfqs", "winner_rank")
        op.drop_column("rfqs", "decided_at")
        op.drop_column("rfqs", "decided_by")
        op.drop_column("rfqs", "decision_reason")
        op.drop_column("rfqs", "winner_quote_id")

"""add covering indexes for foreign keys

Revision ID: 20260121_0001_add_fk_covering_indexes
Revises: 20260120_0004_add_market_price_indexes
Create Date: 2026-01-21
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260121_0001_add_fk_covering_indexes"
down_revision = "20260120_0004_add_market_price_indexes"
branch_labels = None
depends_on = None


INDEXES: list[tuple[str, str]] = [
    ("ix_contracts_counterparty_id", "CREATE INDEX {clause} ix_contracts_counterparty_id ON public.contracts (counterparty_id)"),
    ("ix_contracts_created_by", "CREATE INDEX {clause} ix_contracts_created_by ON public.contracts (created_by)"),
    ("ix_deals_created_by", "CREATE INDEX {clause} ix_deals_created_by ON public.deals (created_by)"),
    ("ix_hedge_exposures_exposure_id", "CREATE INDEX {clause} ix_hedge_exposures_exposure_id ON public.hedge_exposures (exposure_id)"),
    ("ix_hedge_exposures_hedge_id", "CREATE INDEX {clause} ix_hedge_exposures_hedge_id ON public.hedge_exposures (hedge_id)"),
    ("ix_hedge_tasks_exposure_id", "CREATE INDEX {clause} ix_hedge_tasks_exposure_id ON public.hedge_tasks (exposure_id)"),
    ("ix_hedges_counterparty_id", "CREATE INDEX {clause} ix_hedges_counterparty_id ON public.hedges (counterparty_id)"),
    ("ix_hedges_so_id", "CREATE INDEX {clause} ix_hedges_so_id ON public.hedges (so_id)"),
    ("ix_purchase_orders_supplier_id", "CREATE INDEX {clause} ix_purchase_orders_supplier_id ON public.purchase_orders (supplier_id)"),
    ("ix_rfq_invitations_counterparty_id", "CREATE INDEX {clause} ix_rfq_invitations_counterparty_id ON public.rfq_invitations (counterparty_id)"),
    ("ix_rfq_invitations_rfq_id", "CREATE INDEX {clause} ix_rfq_invitations_rfq_id ON public.rfq_invitations (rfq_id)"),
    ("ix_rfq_quotes_counterparty_id", "CREATE INDEX {clause} ix_rfq_quotes_counterparty_id ON public.rfq_quotes (counterparty_id)"),
    ("ix_rfq_quotes_rfq_id", "CREATE INDEX {clause} ix_rfq_quotes_rfq_id ON public.rfq_quotes (rfq_id)"),
    ("ix_rfqs_decided_by", "CREATE INDEX {clause} ix_rfqs_decided_by ON public.rfqs (decided_by)"),
    ("ix_rfqs_hedge_id", "CREATE INDEX {clause} ix_rfqs_hedge_id ON public.rfqs (hedge_id)"),
    ("ix_rfqs_so_id", "CREATE INDEX {clause} ix_rfqs_so_id ON public.rfqs (so_id)"),
    ("ix_rfqs_winner_quote_id", "CREATE INDEX {clause} ix_rfqs_winner_quote_id ON public.rfqs (winner_quote_id)"),
    ("ix_sales_orders_customer_id", "CREATE INDEX {clause} ix_sales_orders_customer_id ON public.sales_orders (customer_id)"),
    ("ix_treasury_decisions_created_by_user_id", "CREATE INDEX {clause} ix_treasury_decisions_created_by_user_id ON public.treasury_decisions (created_by_user_id)"),
    ("ix_treasury_decisions_exposure_id", "CREATE INDEX {clause} ix_treasury_decisions_exposure_id ON public.treasury_decisions (exposure_id)"),
    ("ix_treasury_kyc_overrides_created_by_user_id", "CREATE INDEX {clause} ix_treasury_kyc_overrides_created_by_user_id ON public.treasury_kyc_overrides (created_by_user_id)"),
    ("ix_users_role_id", "CREATE INDEX {clause} ix_users_role_id ON public.users (role_id)"),
    ("ix_workflow_requests_executed_by_user_id", "CREATE INDEX {clause} ix_workflow_requests_executed_by_user_id ON public.workflow_requests (executed_by_user_id)"),
]


def _create_index(sql_template: str, concurrently: bool) -> None:
    clause = "CONCURRENTLY IF NOT EXISTS" if concurrently else "IF NOT EXISTS"
    op.execute(sql_template.format(clause=clause))


def _drop_index(name: str, concurrently: bool) -> None:
    if concurrently:
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}")
    else:
        op.execute(f"DROP INDEX IF EXISTS {name}")


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    concurrently = dialect == "postgresql"
    ctx = op.get_context()
    if concurrently:
        with ctx.autocommit_block():
            for _, sql_template in INDEXES:
                _create_index(sql_template, concurrently=True)
    else:
        for _, sql_template in INDEXES:
            _create_index(sql_template, concurrently=False)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    concurrently = dialect == "postgresql"
    ctx = op.get_context()
    if concurrently:
        with ctx.autocommit_block():
            for name, _ in INDEXES:
                _drop_index(name, concurrently=True)
    else:
        for name, _ in INDEXES:
            _drop_index(name, concurrently=False)

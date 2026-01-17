"""
Contract Tests - Pydantic Schema Validation

These tests ensure that the Pydantic schemas (contracts) remain stable
and compatible with the frontend expectations.

Any breaking change to these schemas should be detected here before
causing runtime issues in the frontend.

Note: This project uses Pydantic v1. Use __fields__ instead of model_fields.
"""

import pytest
from pydantic import ValidationError

from app.schemas.cashflow import CashflowItemRead
from app.schemas.contracts import ContractRead
from app.schemas.counterparties import CounterpartyRead
from app.schemas.deals import DealRead
from app.schemas.exposures import ExposureBase, ExposureRead
from app.schemas.inbox import InboxCounts, InboxDecisionCreate
from app.schemas.pnl import PnlDealAggregateRow
from app.schemas.rfqs import RfqCreate, RfqQuoteCreate, RfqRead
from app.schemas.timeline import TimelineEventRead

# =============================================================================
# Exposure Schema Contracts
# =============================================================================


class TestExposureSchemas:
    """Contract tests for Exposure schemas."""

    def test_exposure_base_required_fields(self):
        """ExposureBase requires source_type, source_id, product, quantity_mt."""
        with pytest.raises(ValidationError) as exc:
            ExposureBase()
        errors = exc.value.errors()
        required = {e["loc"][0] for e in errors if e["type"] == "value_error.missing"}
        assert "source_type" in required
        assert "source_id" in required
        assert "quantity_mt" in required

    def test_exposure_read_includes_id_and_timestamps(self):
        """ExposureRead must include id and created_at fields."""
        fields = ExposureRead.__fields__
        assert "id" in fields
        assert "created_at" in fields


# =============================================================================
# RFQ Schema Contracts
# =============================================================================


class TestRfqSchemas:
    """Contract tests for RFQ schemas."""

    def test_rfq_create_required_fields(self):
        """RfqCreate requires so_id, quantity_mt, period (rfq_number is optional)."""
        with pytest.raises(ValidationError) as exc:
            RfqCreate()
        errors = exc.value.errors()
        required = {e["loc"][0] for e in errors if e["type"] == "value_error.missing"}
        assert "so_id" in required
        assert "quantity_mt" in required
        assert "period" in required

    def test_rfq_read_includes_status(self):
        """RfqRead must include status field."""
        assert "status" in RfqRead.__fields__

    def test_rfq_quote_create_required_fields(self):
        """RfqQuoteCreate requires counterparty_name and quote_price."""
        with pytest.raises(ValidationError) as exc:
            RfqQuoteCreate()
        errors = exc.value.errors()
        required = {e["loc"][0] for e in errors if e["type"] == "value_error.missing"}
        assert "counterparty_name" in required
        assert "quote_price" in required


# =============================================================================
# Contract Schema Contracts
# =============================================================================


class TestContractSchemas:
    """Contract tests for Contract (Trade) schemas."""

    def test_contract_read_includes_core_fields(self):
        """ContractRead must include contract_id, status, and rfq_id."""
        fields = ContractRead.__fields__
        assert "contract_id" in fields
        assert "status" in fields
        assert "rfq_id" in fields


# =============================================================================
# Inbox Schema Contracts
# =============================================================================


class TestInboxSchemas:
    """Contract tests for Inbox schemas."""

    def test_inbox_counts_all_fields_present(self):
        """InboxCounts must have all required count fields."""
        fields = InboxCounts.__fields__
        expected = [
            "purchase_orders_pending",
            "sales_orders_pending",
            "rfqs_draft",
            "rfqs_sent",
            "exposures_active",
            "exposures_passive",
            "exposures_residual",
        ]
        for field in expected:
            assert field in fields, f"Missing field: {field}"

    def test_inbox_decision_create_requires_decision(self):
        """InboxDecisionCreate requires decision field."""
        with pytest.raises(ValidationError) as exc:
            InboxDecisionCreate()
        errors = exc.value.errors()
        required = {e["loc"][0] for e in errors if e["type"] == "value_error.missing"}
        assert "decision" in required


# =============================================================================
# Timeline Schema Contracts
# =============================================================================


class TestTimelineSchemas:
    """Contract tests for Timeline schemas."""

    def test_timeline_event_read_includes_core_fields(self):
        """TimelineEventRead must include event_type, subject_type, subject_id."""
        fields = TimelineEventRead.__fields__
        assert "event_type" in fields
        assert "subject_type" in fields
        assert "subject_id" in fields
        assert "created_at" in fields


# =============================================================================
# Counterparty Schema Contracts
# =============================================================================


class TestCounterpartySchemas:
    """Contract tests for Counterparty schemas."""

    def test_counterparty_read_includes_id(self):
        """CounterpartyRead must include id field."""
        assert "id" in CounterpartyRead.__fields__


# =============================================================================
# Deal Schema Contracts
# =============================================================================


class TestDealSchemas:
    """Contract tests for Deal schemas."""

    def test_deal_read_includes_core_fields(self):
        """DealRead must include id and deal_uuid fields."""
        fields = DealRead.__fields__
        assert "id" in fields
        assert "deal_uuid" in fields
        assert "currency" in fields


# =============================================================================
# P&L Schema Contracts
# =============================================================================


class TestPnlSchemas:
    """Contract tests for P&L schemas."""

    def test_pnl_deal_aggregate_row_includes_core_fields(self):
        """PnlDealAggregateRow must include deal and P&L-related fields."""
        fields = PnlDealAggregateRow.__fields__
        assert "deal_id" in fields
        assert "total_pnl_usd" in fields
        assert "realized_pnl_usd" in fields


# =============================================================================
# Cashflow Schema Contracts
# =============================================================================


class TestCashflowSchemas:
    """Contract tests for Cashflow schemas."""

    def test_cashflow_item_includes_contract_and_date(self):
        """CashflowItemRead must include contract_id and settlement_date fields."""
        fields = CashflowItemRead.__fields__
        assert "contract_id" in fields
        assert "settlement_date" in fields


# =============================================================================
# Schema Stability Tests
# =============================================================================


class TestSchemaStability:
    """Tests to ensure schemas can be serialized/deserialized correctly."""

    def test_inbox_counts_serialization(self):
        """InboxCounts should serialize to JSON correctly."""
        counts = InboxCounts(
            purchase_orders_pending=5,
            sales_orders_pending=3,
            rfqs_draft=2,
            rfqs_sent=1,
            exposures_active=10,
            exposures_passive=5,
            exposures_residual=2,
        )
        data = counts.dict()
        assert data["purchase_orders_pending"] == 5
        assert data["exposures_active"] == 10

    def test_inbox_decision_create_with_justification(self):
        """InboxDecisionCreate should accept decision and justification."""
        decision = InboxDecisionCreate(
            decision="no_hedge",
            justification="Market conditions unfavorable",
        )
        assert decision.decision == "no_hedge"
        assert decision.justification == "Market conditions unfavorable"

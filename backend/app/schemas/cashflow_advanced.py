from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ScenarioName = Literal["base", "optimistic", "pessimistic"]
BaselineMethod = Literal["explicit_assumption", "proxy_3m"]
FxMode = Literal["explicit", "policy_map"]


class CashflowAdvancedFilters(BaseModel):
    contract_id: Optional[str] = None
    deal_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    settlement_date_from: Optional[date] = None
    settlement_date_to: Optional[date] = None
    limit: int = Field(default=200, ge=1, le=1000)


class CashflowAdvancedFx(BaseModel):
    mode: FxMode = "explicit"
    fx_symbol: Optional[str] = None
    fx_source: Optional[str] = None
    policy_key: Optional[str] = None


class CashflowAdvancedReporting(BaseModel):
    reporting_currency: Optional[str] = None
    fx: Optional[CashflowAdvancedFx] = None


class CashflowAdvancedScenario(BaseModel):
    baseline_method: BaselineMethod = "explicit_assumption"
    aliases_enabled: bool = True
    sensitivities_pct: List[float] = Field(default_factory=lambda: [-0.10, -0.05, 0.05, 0.10])


class CashflowAdvancedAssumptions(BaseModel):
    forward_price_assumption: Optional[float] = None
    forward_price_currency: str = "USD"
    forward_price_symbol: Optional[str] = None
    forward_price_as_of: Optional[date] = None
    notes: Optional[str] = None


class CashflowAdvancedPreviewRequest(BaseModel):
    as_of: date
    filters: CashflowAdvancedFilters = Field(default_factory=CashflowAdvancedFilters)
    reporting: Optional[CashflowAdvancedReporting] = None
    scenario: CashflowAdvancedScenario = Field(default_factory=CashflowAdvancedScenario)
    assumptions: CashflowAdvancedAssumptions = Field(default_factory=CashflowAdvancedAssumptions)


class CashflowAdvancedReferences(BaseModel):
    cash_last_published_date: Optional[date] = None
    proxy_3m_last_published_date: Optional[date] = None

    fx_as_of: Optional[datetime] = None
    fx_rate: Optional[float] = None
    fx_symbol: Optional[str] = None
    fx_source: Optional[str] = None


class CashflowAdvancedProjection(BaseModel):
    scenario: ScenarioName
    sensitivity_pct: float

    expected_settlement_value_usd: Optional[float] = None
    pnl_current_unrealized_usd: Optional[float] = None
    future_pnl_impact_usd: Optional[float] = None

    expected_settlement_value_reporting: Optional[float] = None
    pnl_current_unrealized_reporting: Optional[float] = None
    future_pnl_impact_reporting: Optional[float] = None

    methodology: str
    flags: List[str] = Field(default_factory=list)


class CashflowAdvancedItem(BaseModel):
    contract_id: str
    deal_id: int
    rfq_id: int
    counterparty_id: Optional[int] = None
    settlement_date: Optional[date] = None

    bucket_date: Optional[date] = None
    native_currency: str = "USD"

    # Explicit, pre-materialized metadata for frontend (no inference required).
    references: CashflowAdvancedReferences
    methodologies: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)

    projections: List[CashflowAdvancedProjection]


class CashflowAdvancedAggregateRow(BaseModel):
    bucket_date: date
    counterparty_id: Optional[int] = None
    deal_id: Optional[int] = None
    currency: str

    scenario: ScenarioName
    sensitivity_pct: float

    expected_settlement_total: Optional[float] = None
    pnl_current_unrealized_total: Optional[float] = None
    future_pnl_impact_total: Optional[float] = None

    # Explicit, pre-materialized metadata for frontend (no inference required).
    references: CashflowAdvancedReferences
    methodologies: List[str] = Field(default_factory=list)

    flags: List[str] = Field(default_factory=list)


class CashflowAdvancedBucketTotalRow(BaseModel):
    bucket_date: date
    currency: str

    scenario: ScenarioName
    sensitivity_pct: float

    expected_settlement_total: Optional[float] = None
    pnl_current_unrealized_total: Optional[float] = None
    future_pnl_impact_total: Optional[float] = None

    references: CashflowAdvancedReferences
    methodologies: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)


class CashflowAdvancedPreviewResponse(BaseModel):
    inputs_hash: str
    as_of: date
    assumptions: CashflowAdvancedAssumptions
    references: CashflowAdvancedReferences
    items: List[CashflowAdvancedItem]

    # Totals per bucket_date (pre-materialized for deterministic rendering).
    bucket_totals: List[CashflowAdvancedBucketTotalRow]

    # Consolidation per (bucket_date, counterparty, deal, currency, scenario, sensitivity).
    aggregates: List[CashflowAdvancedAggregateRow]

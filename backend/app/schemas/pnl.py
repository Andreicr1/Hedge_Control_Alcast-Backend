from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class PnlSnapshotRequest(BaseModel):
    as_of_date: date
    filters: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class PnlUnrealizedPreview(BaseModel):
    contract_id: str
    deal_id: int
    as_of_date: date
    unrealized_pnl_usd: float
    methodology: Optional[str] = None
    data_quality_flags: List[str] = Field(default_factory=list)


class PnlRealizedPreview(BaseModel):
    contract_id: str
    deal_id: int
    settlement_date: date
    realized_pnl_usd: float
    methodology: Optional[str] = None
    data_quality_flags: List[str] = Field(default_factory=list)
    locked_at: datetime


class PnlSnapshotPlanRead(BaseModel):
    as_of_date: date
    filters: Dict[str, Any]
    inputs_hash: str
    active_contract_ids: List[str]
    settled_contract_ids: List[str]


class PnlSnapshotDryRunRead(BaseModel):
    kind: Literal["dry_run"] = "dry_run"
    plan: PnlSnapshotPlanRead
    active_contracts: int
    settled_contracts: int
    unrealized_preview: List[PnlUnrealizedPreview]
    realized_preview: List[PnlRealizedPreview]


class PnlSnapshotMaterializeRead(BaseModel):
    kind: Literal["materialized"] = "materialized"
    run_id: int
    inputs_hash: str
    unrealized_written: int
    unrealized_updated: int
    realized_locked_written: int


PnlSnapshotExecuteResponse = Union[PnlSnapshotDryRunRead, PnlSnapshotMaterializeRead]


class PnlDealAggregateRow(BaseModel):
    deal_id: int
    currency: str = "USD"
    unrealized_pnl_usd: float
    realized_pnl_usd: float
    total_pnl_usd: float


class PnlAggregateResponse(BaseModel):
    as_of_date: date
    currency: str = "USD"
    rows: List[PnlDealAggregateRow]
    unrealized_total_usd: float
    realized_total_usd: float
    total_pnl_usd: float


class PnlContractSnapshotRead(BaseModel):
    contract_id: str
    deal_id: int
    as_of_date: date
    currency: str
    unrealized_pnl_usd: float
    methodology: Optional[str] = None
    data_quality_flags: List[str] = Field(default_factory=list)
    inputs_hash: str

    class Config:
        orm_mode = True


class PnlContractRealizedRead(BaseModel):
    contract_id: str
    deal_id: int
    settlement_date: date
    currency: str
    realized_pnl_usd: float
    methodology: Optional[str] = None
    inputs_hash: str
    locked_at: datetime
    source_hint: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True


class PnlContractDetailResponse(BaseModel):
    contract_id: str
    as_of_date: date
    currency: str = "USD"
    unrealized: Optional[PnlContractSnapshotRead] = None
    realized_locks: List[PnlContractRealizedRead] = Field(default_factory=list)
    realized_total_usd: float
    total_pnl_usd: float

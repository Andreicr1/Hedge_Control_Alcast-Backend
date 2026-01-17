from __future__ import annotations

from datetime import date
from typing import Iterable, List

from sqlalchemy.orm import Session

from app import models
from app.schemas.cashflow import CashflowItemRead
from app.services.contract_mtm_service import (
    ContractMtmResult,
    compute_mtm_for_contract_avg,
    compute_settlement_value_for_contract_avg,
)


def _apply_mtm_result_to_item(
    item: CashflowItemRead,
    res: ContractMtmResult,
    *,
    kind: str,
) -> None:
    if kind == "projected":
        item.projected_value_usd = float(res.mtm_usd)
        item.projected_methodology = res.methodology
        item.projected_as_of = res.as_of_date
    elif kind == "final":
        item.final_value_usd = float(res.mtm_usd)
        item.final_methodology = res.methodology
    else:
        raise ValueError("invalid kind")

    item.observation_start = res.observation_start
    item.observation_end_used = res.observation_end_used
    item.last_published_cash_date = res.last_published_cash_date


def build_cashflow_items(
    db: Session,
    contracts: Iterable[models.Contract],
    *,
    as_of: date,
) -> List[CashflowItemRead]:
    out: List[CashflowItemRead] = []

    for c in contracts:
        flags: list[str] = []

        item = CashflowItemRead(
            contract_id=c.contract_id,
            deal_id=c.deal_id,
            rfq_id=c.rfq_id,
            counterparty_id=c.counterparty_id,
            settlement_date=c.settlement_date,
            data_quality_flags=flags,
        )

        if c.settlement_date is None:
            flags.append("missing_settlement_date")
        else:
            projected = compute_mtm_for_contract_avg(db, c, as_of_date=as_of)
            if projected is None:
                flags.append("projected_not_available")
            else:
                _apply_mtm_result_to_item(item, projected, kind="projected")

            # Only consider final values on/after settlement date.
            if as_of >= c.settlement_date:
                final_val = compute_settlement_value_for_contract_avg(db, c)
                if final_val is None:
                    flags.append("final_not_available")
                else:
                    _apply_mtm_result_to_item(item, final_val, kind="final")

        out.append(item)

    return out

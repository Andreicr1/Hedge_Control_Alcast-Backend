from __future__ import annotations

import os
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

    contracts_list = list(contracts)
    contract_ids = [str(c.contract_id) for c in contracts_list]

    baseline_by_contract: dict[str, models.CashflowBaselineItem] = {}
    if contract_ids:
        rows = (
            db.query(models.CashflowBaselineItem)
            .filter(models.CashflowBaselineItem.contract_id.in_(sorted(set(contract_ids))))
            .filter(models.CashflowBaselineItem.as_of_date == as_of)
            .filter(models.CashflowBaselineItem.currency == "USD")
            .all()
        )
        for row in rows:
            baseline_by_contract[str(row.contract_id)] = row

    def _apply_mtm_snapshot(item: CashflowItemRead, m: models.MtmContractSnapshot) -> None:
        item.projected_value_usd = float(m.mtm_usd)
        item.projected_methodology = str(m.methodology) if m.methodology else None
        item.projected_as_of = as_of

        refs = dict(m.references or {})
        try:
            item.observation_start = refs.get("observation_start")
        except Exception:
            pass
        try:
            item.observation_end_used = refs.get("observation_end_used")
        except Exception:
            pass
        try:
            item.last_published_cash_date = refs.get("last_published_cash_date")
        except Exception:
            pass

    for c in contracts_list:
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
            baseline = baseline_by_contract.get(str(c.contract_id))
            if baseline is not None:
                item.projected_value_usd = baseline.projected_value_usd
                item.projected_methodology = baseline.projected_methodology
                item.projected_as_of = baseline.projected_as_of
                item.final_value_usd = baseline.final_value_usd
                item.final_methodology = baseline.final_methodology
                item.observation_start = baseline.observation_start
                item.observation_end_used = baseline.observation_end_used
                item.last_published_cash_date = baseline.last_published_cash_date
                if baseline.data_quality_flags:
                    flags.extend([str(f) for f in baseline.data_quality_flags])
            else:
                flags.append("baseline_not_available")

                allow_legacy = str(
                    os.getenv("CASHFLOW_ALLOW_LEGACY_FALLBACK", "false")
                ).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                }
                if allow_legacy:
                    projected = compute_mtm_for_contract_avg(db, c, as_of_date=as_of)
                    if projected is None:
                        flags.append("projected_not_available")
                    else:
                        _apply_mtm_result_to_item(item, projected, kind="projected")

                    if as_of >= c.settlement_date:
                        final_val = compute_settlement_value_for_contract_avg(db, c)
                        if final_val is None:
                            flags.append("final_not_available")
                        else:
                            _apply_mtm_result_to_item(item, final_val, kind="final")

        out.append(item)

    return out

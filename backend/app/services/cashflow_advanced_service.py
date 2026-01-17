from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models
from app.schemas.cashflow_advanced import (
    CashflowAdvancedAggregateRow,
    CashflowAdvancedBucketTotalRow,
    CashflowAdvancedItem,
    CashflowAdvancedPreviewRequest,
    CashflowAdvancedPreviewResponse,
    CashflowAdvancedProjection,
    CashflowAdvancedReferences,
)
from app.services.contract_mtm_service import (
    AL_CASH_SETTLEMENT_SYMBOL,
    _cash_price_by_day,
    _extract_avg_window_from_trade_specs,
    _extract_fixed_price_and_side,
    _extract_quantity_mt,
    _latest_cash_publish_date,
    compute_realized_avg_cash,
)

_VERSION = "cashflow.advanced.preview.v1"
_PROXY_3M_SYMBOL = "ALUMINUM_3M_SETTLEMENT"

_SCENARIO_ORDER = {
    "base": 0,
    "optimistic": 1,
    "pessimistic": 2,
}


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items() if val is not None}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    return str(v)


def compute_cashflow_advanced_inputs_hash(payload: CashflowAdvancedPreviewRequest) -> str:
    # Pydantic v1 compatibility: use .dict() (v2 would be model_dump).
    raw_payload = payload.dict()
    data = {
        "version": _VERSION,
        **_jsonable(raw_payload),
    }
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def _as_of_end_dt(as_of: date) -> datetime:
    return datetime.combine(as_of, time(23, 59, 59), tzinfo=timezone.utc)


def _latest_market_price(
    db: Session,
    *,
    symbol: str,
    as_of: date,
    source: Optional[str] = None,
    fx_only: bool = False,
) -> Optional[models.MarketPrice]:
    q = db.query(models.MarketPrice).filter(models.MarketPrice.symbol == symbol)
    if source:
        q = q.filter(models.MarketPrice.source == source)
    if fx_only:
        q = q.filter(models.MarketPrice.fx.is_(True))

    cutoff = _as_of_end_dt(as_of)
    q = q.filter(models.MarketPrice.as_of <= cutoff)
    return q.order_by(models.MarketPrice.as_of.desc(), models.MarketPrice.created_at.desc()).first()


def _resolve_fx_rate(
    db: Session,
    *,
    as_of: date,
    reporting_currency: Optional[str],
    fx_mode: Optional[str],
    fx_symbol: Optional[str],
    fx_source: Optional[str],
    policy_key: Optional[str],
) -> tuple[Optional[float], Optional[datetime], Optional[str], Optional[str]]:
    if not reporting_currency or reporting_currency.upper() == "USD":
        return None, None, None, None

    # policy_map is supported as a deterministic alias to explicit parameters for now.
    if fx_mode == "policy_map" and policy_key and (not fx_symbol or not fx_source):
        # format: "BRL:USDBRL=X@yahoo" -> take right side
        try:
            rhs = policy_key.split(":", 1)[1]
            fx_symbol, fx_source = rhs.split("@", 1)
        except Exception:
            pass

    if not fx_symbol:
        return None, None, fx_symbol, fx_source

    fx = _latest_market_price(db, symbol=fx_symbol, as_of=as_of, source=fx_source, fx_only=True)
    if not fx:
        # fallback: accept non-fx flagged
        fx = _latest_market_price(
            db,
            symbol=fx_symbol,
            as_of=as_of,
            source=fx_source,
            fx_only=False,
        )
    if not fx:
        return None, None, fx_symbol, fx_source
    return float(fx.price), fx.as_of, fx.symbol, fx.source


@dataclass(frozen=True)
class _ExpectedSettlementPlan:
    expected_settlement_value_usd: float
    methodology: str
    flags: list[str]


def _expected_settlement_value_for_contract(
    db: Session,
    *,
    contract: models.Contract,
    as_of: date,
    baseline_method: str,
    forward_price_assumption: Optional[float],
    forward_price_currency: str,
    sensitivity_pct: float,
    references: CashflowAdvancedReferences,
) -> Optional[_ExpectedSettlementPlan]:
    flags: list[str] = []

    if (forward_price_currency or "USD").upper() != "USD":
        flags.append("currency_not_supported")
        return None

    rfq = db.get(models.Rfq, contract.rfq_id)
    idx = int(getattr(contract, "trade_index", None) or 0)
    spec = None
    if rfq and getattr(rfq, "trade_specs", None) and idx < len(rfq.trade_specs or []):
        spec = rfq.trade_specs[idx]
    if not isinstance(spec, dict):
        flags.append("projected_not_available")
        return None

    obs_start, obs_end = _extract_avg_window_from_trade_specs(spec)
    if not obs_start or not obs_end:
        flags.append("projected_not_available")
        return None

    fixed_price, fixed_side = _extract_fixed_price_and_side(contract.trade_snapshot or {})
    if fixed_price is None or fixed_side not in {"buy", "sell"}:
        flags.append("projected_not_available")
        return None

    qty = _extract_quantity_mt(contract.trade_snapshot or {}, rfq)
    if qty == 0.0:
        flags.append("projected_not_available")
        return None

    last_published_cash = _latest_cash_publish_date(db)
    references.cash_last_published_date = references.cash_last_published_date or last_published_cash

    realized_avg, end_used, last_published = compute_realized_avg_cash(
        db,
        obs_start,
        obs_end,
        as_of_date=as_of,
    )
    references.cash_last_published_date = references.cash_last_published_date or last_published

    if realized_avg is None or end_used is None:
        flags.append("projected_not_available")
        return None

    total_days = (obs_end - obs_start).days + 1
    observed_calendar_days = (end_used - obs_start).days + 1
    remaining_days = max(0, total_days - observed_calendar_days)

    # Determine baseline for the non-observed portion.
    baseline_price: Optional[float] = None
    baseline_source = ""

    if forward_price_assumption is not None:
        baseline_price = float(forward_price_assumption)
        baseline_source = "baseline.explicit_assumption"
    else:
        flags.append("assumptions_missing")
        if baseline_method == "proxy_3m":
            mp = _latest_market_price(db, symbol=_PROXY_3M_SYMBOL, as_of=as_of, source="westmetall")
            if mp is not None:
                baseline_price = float(mp.price)
                baseline_source = "baseline.proxy_3m.westmetall"
                references.proxy_3m_last_published_date = (
                    references.proxy_3m_last_published_date or mp.as_of.date()
                )
            else:
                flags.append("proxy_3m_not_available")

    if remaining_days > 0 and baseline_price is None:
        flags.append("projected_not_available")
        return None

    # Optional data quality: detect missing days in the observed calendar window.
    series = _cash_price_by_day(db, obs_start, end_used)
    observed_expected_days = observed_calendar_days
    if len(series) < observed_expected_days:
        flags.append("market_data_missing_days")

    adjusted_baseline = baseline_price
    if adjusted_baseline is not None:
        adjusted_baseline = float(adjusted_baseline) * (1.0 + float(sensitivity_pct))

    expected_final_avg = (
        float(realized_avg) * float(observed_calendar_days)
        + (
            float(adjusted_baseline) * float(remaining_days)
            if adjusted_baseline is not None
            else 0.0
        )
    ) / float(total_days)

    sign = 1.0 if fixed_side == "buy" else -1.0
    expected_value = (expected_final_avg - float(fixed_price)) * float(qty) * sign

    methodology = "contract.avg.expected_final_avg"
    if baseline_source:
        methodology = f"{methodology}|{baseline_source}"
    methodology = f"{methodology}|driver={AL_CASH_SETTLEMENT_SYMBOL}"

    return _ExpectedSettlementPlan(
        expected_settlement_value_usd=float(expected_value),
        methodology=methodology,
        flags=flags,
    )


def build_cashflow_advanced_preview(
    db: Session,
    *,
    payload: CashflowAdvancedPreviewRequest,
) -> CashflowAdvancedPreviewResponse:
    inputs_hash = compute_cashflow_advanced_inputs_hash(payload)

    as_of = payload.as_of
    refs = CashflowAdvancedReferences()

    reporting_currency = None
    fx_mode = None
    fx_symbol = None
    fx_source = None
    policy_key = None

    if payload.reporting:
        reporting_currency = payload.reporting.reporting_currency
        if payload.reporting.fx:
            fx_mode = payload.reporting.fx.mode
            fx_symbol = payload.reporting.fx.fx_symbol
            fx_source = payload.reporting.fx.fx_source
            policy_key = payload.reporting.fx.policy_key

    fx_rate, fx_as_of, fx_symbol_used, fx_source_used = _resolve_fx_rate(
        db,
        as_of=as_of,
        reporting_currency=reporting_currency,
        fx_mode=fx_mode,
        fx_symbol=fx_symbol,
        fx_source=fx_source,
        policy_key=policy_key,
    )
    if fx_rate is not None:
        refs.fx_rate = fx_rate
        refs.fx_as_of = fx_as_of
        refs.fx_symbol = fx_symbol_used
        refs.fx_source = fx_source_used

    f = payload.filters
    q = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
    )

    if f.contract_id is not None:
        q = q.filter(models.Contract.contract_id == f.contract_id)
    if f.counterparty_id is not None:
        q = q.filter(models.Contract.counterparty_id == f.counterparty_id)
    if f.deal_id is not None:
        q = q.filter(models.Contract.deal_id == f.deal_id)
    if f.settlement_date_from is not None:
        q = q.filter(models.Contract.settlement_date >= f.settlement_date_from)
    if f.settlement_date_to is not None:
        q = q.filter(models.Contract.settlement_date <= f.settlement_date_to)

    contracts = (
        q.order_by(
            models.Contract.settlement_date.asc(),
            models.Contract.deal_id.asc(),
            models.Contract.contract_id.asc(),
        )
        .limit(int(f.limit))
        .all()
    )

    # Build the sensitivity grid.
    pct_set = {0.0}
    for x in payload.scenario.sensitivities_pct:
        try:
            pct_set.add(float(x))
        except Exception:
            continue

    if payload.scenario.aliases_enabled:
        pct_set.update({0.0, 0.05, -0.05})

    sensitivity_grid = sorted(pct_set)

    items: list[CashflowAdvancedItem] = []

    # Aggregation key: (bucket_date, counterparty_id, deal_id, currency, scenario, sensitivity_pct)
    aggregates: dict[
        tuple[date, Optional[int], Optional[int], str, str, float],
        dict[str, Any],
    ] = {}

    # Totals by bucket_date (frontend-ready; no inference required)
    bucket_totals: dict[tuple[date, str, str, float], dict[str, Any]] = {}

    for c in contracts:
        item_flags: list[str] = []
        item_methodologies: set[str] = set()
        bucket_date = c.settlement_date
        if bucket_date is None:
            item_flags.append("missing_settlement_date")
            continue

        pnl_row = (
            db.query(models.PnlContractSnapshot)
            .filter(models.PnlContractSnapshot.contract_id == c.contract_id)
            .filter(models.PnlContractSnapshot.as_of_date == as_of)
            .filter(models.PnlContractSnapshot.currency == "USD")
            .first()
        )
        pnl_unreal = float(pnl_row.unrealized_pnl_usd) if pnl_row else None

        projections: list[CashflowAdvancedProjection] = []

        for pct in sensitivity_grid:
            scenario_name = "base"
            if payload.scenario.aliases_enabled:
                if abs(pct - 0.05) < 1e-12:
                    scenario_name = "optimistic"
                elif abs(pct + 0.05) < 1e-12:
                    scenario_name = "pessimistic"

            flags: list[str] = []
            if pnl_unreal is None:
                flags.append("pnl_not_available")

            plan = _expected_settlement_value_for_contract(
                db,
                contract=c,
                as_of=as_of,
                baseline_method=payload.scenario.baseline_method,
                forward_price_assumption=payload.assumptions.forward_price_assumption,
                forward_price_currency=payload.assumptions.forward_price_currency,
                sensitivity_pct=float(pct),
                references=refs,
            )

            expected_usd: Optional[float] = None
            methodology = "not_available"
            if plan is None:
                flags.append("projected_not_available")
            else:
                expected_usd = plan.expected_settlement_value_usd
                methodology = plan.methodology
                flags.extend(plan.flags)

            future_impact_usd: Optional[float] = None
            if expected_usd is not None and pnl_unreal is not None:
                future_impact_usd = float(expected_usd) - float(pnl_unreal)

            expected_reporting = None
            pnl_reporting = None
            impact_reporting = None
            if reporting_currency and reporting_currency.upper() != "USD":
                if fx_rate is None:
                    flags.append("fx_not_available")
                else:
                    if expected_usd is not None:
                        expected_reporting = float(expected_usd) * float(fx_rate)
                    if pnl_unreal is not None:
                        pnl_reporting = float(pnl_unreal) * float(fx_rate)
                    if future_impact_usd is not None:
                        impact_reporting = float(future_impact_usd) * float(fx_rate)

            proj = CashflowAdvancedProjection(
                scenario=scenario_name,  # type: ignore[arg-type]
                sensitivity_pct=float(pct),
                expected_settlement_value_usd=expected_usd,
                pnl_current_unrealized_usd=pnl_unreal,
                future_pnl_impact_usd=future_impact_usd,
                expected_settlement_value_reporting=expected_reporting,
                pnl_current_unrealized_reporting=pnl_reporting,
                future_pnl_impact_reporting=impact_reporting,
                methodology=methodology,
                flags=sorted(set(flags)),
            )
            projections.append(proj)
            item_methodologies.add(methodology)
            item_flags.extend(proj.flags)

            currency = "USD"
            use_reporting = (
                reporting_currency and reporting_currency.upper() != "USD" and fx_rate is not None
            )
            if use_reporting:
                currency = reporting_currency.upper()

            key = (
                bucket_date,
                c.counterparty_id,
                c.deal_id,
                currency,
                scenario_name,
                float(pct),
            )
            agg = aggregates.get(key)
            if not agg:
                agg = {
                    "expected_settlement_total": 0.0,
                    "pnl_current_unrealized_total": 0.0,
                    "future_pnl_impact_total": 0.0,
                    "flags": set(),
                    "methodologies": set(),
                    "has_any": False,
                }
                aggregates[key] = agg

            if use_reporting:
                ev = expected_reporting
                pu = pnl_reporting
                fi = impact_reporting
            else:
                ev = expected_usd
                pu = pnl_unreal
                fi = future_impact_usd

            if ev is not None:
                agg["expected_settlement_total"] += float(ev)
                agg["has_any"] = True
            if pu is not None:
                agg["pnl_current_unrealized_total"] += float(pu)
                agg["has_any"] = True
            if fi is not None:
                agg["future_pnl_impact_total"] += float(fi)
                agg["has_any"] = True
            for fl in proj.flags:
                agg["flags"].add(fl)
            agg["methodologies"].add(proj.methodology)

            bt_key = (bucket_date, currency, scenario_name, float(pct))
            bt = bucket_totals.get(bt_key)
            if not bt:
                bt = {
                    "expected_settlement_total": 0.0,
                    "pnl_current_unrealized_total": 0.0,
                    "future_pnl_impact_total": 0.0,
                    "flags": set(),
                    "methodologies": set(),
                    "has_any": False,
                }
                bucket_totals[bt_key] = bt

            if ev is not None:
                bt["expected_settlement_total"] += float(ev)
                bt["has_any"] = True
            if pu is not None:
                bt["pnl_current_unrealized_total"] += float(pu)
                bt["has_any"] = True
            if fi is not None:
                bt["future_pnl_impact_total"] += float(fi)
                bt["has_any"] = True
            for fl in proj.flags:
                bt["flags"].add(fl)
            bt["methodologies"].add(proj.methodology)

        projections.sort(
            key=lambda p: (
                _SCENARIO_ORDER.get(str(p.scenario), 99),
                float(p.sensitivity_pct),
            )
        )

        projections.sort(
            key=lambda p: (
                _SCENARIO_ORDER.get(str(p.scenario), 99),
                float(p.sensitivity_pct),
            )
        )

        items.append(
            CashflowAdvancedItem(
                contract_id=c.contract_id,
                deal_id=c.deal_id,
                rfq_id=c.rfq_id,
                counterparty_id=c.counterparty_id,
                settlement_date=c.settlement_date,
                bucket_date=bucket_date,
                native_currency="USD",
                references=refs,
                methodologies=sorted(item_methodologies),
                flags=sorted(set(item_flags)),
                projections=projections,
            )
        )

    agg_rows: list[CashflowAdvancedAggregateRow] = []
    for (bucket_date, counterparty_id, deal_id, currency, scenario_name, pct), data in sorted(
        aggregates.items(),
        key=lambda x: (
            x[0][0],
            x[0][2] or 0,
            x[0][1] or 0,
            x[0][3],
            _SCENARIO_ORDER.get(x[0][4], 99),
            x[0][5],
        ),
    ):
        if not data.get("has_any"):
            continue
        agg_rows.append(
            CashflowAdvancedAggregateRow(
                bucket_date=bucket_date,
                counterparty_id=counterparty_id,
                deal_id=deal_id,
                currency=currency,
                scenario=scenario_name,  # type: ignore[arg-type]
                sensitivity_pct=float(pct),
                expected_settlement_total=float(data["expected_settlement_total"]),
                pnl_current_unrealized_total=float(data["pnl_current_unrealized_total"]),
                future_pnl_impact_total=float(data["future_pnl_impact_total"]),
                references=refs,
                methodologies=sorted(list(data["methodologies"])),
                flags=sorted(list(data["flags"])),
            )
        )

    bucket_rows: list[CashflowAdvancedBucketTotalRow] = []
    for (bucket_date, currency, scenario_name, pct), data in sorted(
        bucket_totals.items(),
        key=lambda x: (
            x[0][0],
            x[0][1],
            _SCENARIO_ORDER.get(x[0][2], 99),
            x[0][3],
        ),
    ):
        if not data.get("has_any"):
            continue
        bucket_rows.append(
            CashflowAdvancedBucketTotalRow(
                bucket_date=bucket_date,
                currency=currency,
                scenario=scenario_name,  # type: ignore[arg-type]
                sensitivity_pct=float(pct),
                expected_settlement_total=float(data["expected_settlement_total"]),
                pnl_current_unrealized_total=float(data["pnl_current_unrealized_total"]),
                future_pnl_impact_total=float(data["future_pnl_impact_total"]),
                references=refs,
                methodologies=sorted(list(data["methodologies"])),
                flags=sorted(list(data["flags"])),
            )
        )

    return CashflowAdvancedPreviewResponse(
        inputs_hash=inputs_hash,
        as_of=as_of,
        assumptions=payload.assumptions,
        references=refs,
        items=items,
        bucket_totals=bucket_rows,
        aggregates=agg_rows,
    )

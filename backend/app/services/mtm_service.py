from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.services.lme_price_service import latest_lme_price_prefer_types


@dataclass
class MtmComputation:
    mtm_value: float
    fx_rate: Optional[float]
    scenario_mtm_value: Optional[float] = None
    price_used: Optional[float] = None


def _normalize_fx_symbol(sym: Optional[str]) -> Optional[str]:
    s = (sym or "").strip()
    if not s:
        return None
    if s.startswith("^"):
        return s
    # Yahoo FX format (e.g. USDBRL=X) -> ^USDBRL
    if s.upper().endswith("=X") and len(s) == 8 and s[:6].isalpha():
        return f"^{s[:6].upper()}"
    return s


def _latest_fx_rate(
    db: Session,
    fx_symbol: Optional[str],
    source: Optional[str] = None,
) -> Optional[float]:
    fx_symbol_norm = _normalize_fx_symbol(fx_symbol)
    if not fx_symbol_norm:
        return None

    # Use the latest known close; fall back to live if close is missing.
    row = latest_lme_price_prefer_types(
        db,
        symbol=fx_symbol_norm,
        as_of=datetime.now(timezone.utc).date(),
        price_types=["close", "official", "live"],
        market="FX",
        source=source,
    )
    return float(row.price) if row is not None else None


def _apply_price_adjustments(
    price: float,
    haircut_pct: Optional[float],
    price_shift: Optional[float],
) -> float:
    adjusted = price
    if haircut_pct is not None:
        adjusted *= 1 - haircut_pct / 100
    if price_shift is not None:
        adjusted += price_shift
    return adjusted


def compute_mtm_for_hedge(
    db: Session,
    hedge_id: int,
    fx_symbol: Optional[str] = None,
    pricing_source: Optional[str] = None,
    haircut_pct: Optional[float] = None,
    price_shift: Optional[float] = None,
) -> Optional[MtmComputation]:
    hedge = db.get(models.Hedge, hedge_id)
    if not hedge:
        return None
    if hedge.current_market_price is None:
        return None

    price = hedge.current_market_price
    fx_rate = _latest_fx_rate(db, fx_symbol, pricing_source)
    adjusted_price = _apply_price_adjustments(price, haircut_pct, price_shift)
    base_diff = price - hedge.contract_price
    scenario_diff = adjusted_price - hedge.contract_price
    mtm_value = base_diff * hedge.quantity_mt
    scenario_mtm_value = None
    if haircut_pct is not None or price_shift is not None:
        scenario_mtm_value = scenario_diff * hedge.quantity_mt

    if fx_rate is not None:
        mtm_value *= fx_rate
        if scenario_mtm_value is not None:
            scenario_mtm_value *= fx_rate

    return MtmComputation(
        mtm_value=mtm_value,
        fx_rate=fx_rate,
        scenario_mtm_value=scenario_mtm_value,
        price_used=price,
    )


def compute_mtm_for_order(
    db: Session,
    order_id: int,
    is_purchase: bool,
    fx_symbol: Optional[str] = None,
    pricing_source: Optional[str] = None,
    haircut_pct: Optional[float] = None,
    price_shift: Optional[float] = None,
) -> Optional[MtmComputation]:
    if is_purchase:
        return None
    hedges = db.query(models.Hedge).filter(models.Hedge.so_id == order_id).all()
    if not hedges:
        return None

    total = 0.0
    fx_rate_used: Optional[float] = None
    scenario_total = 0.0
    scenario_present = False
    for h in hedges:
        res = compute_mtm_for_hedge(
            db,
            h.id,
            fx_symbol=fx_symbol,
            pricing_source=pricing_source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
        if res is None:
            continue
        total += res.mtm_value
        fx_rate_used = fx_rate_used or res.fx_rate
        if res.scenario_mtm_value is not None:
            scenario_present = True
            scenario_total += res.scenario_mtm_value
    if total == 0.0 and not scenario_present:
        return None
    return MtmComputation(
        mtm_value=total,
        fx_rate=fx_rate_used,
        scenario_mtm_value=scenario_total if scenario_present else None,
        price_used=None,
    )


def compute_mtm_portfolio(
    db: Session,
    fx_symbol: Optional[str] = None,
    pricing_source: Optional[str] = None,
    haircut_pct: Optional[float] = None,
    price_shift: Optional[float] = None,
) -> Optional[MtmComputation]:
    hedge_ids = [h.id for h in db.query(models.Hedge.id).all()]
    if not hedge_ids:
        return MtmComputation(mtm_value=0.0, fx_rate=None, scenario_mtm_value=None, price_used=None)
    total = 0.0
    fx_rate_used: Optional[float] = None
    scenario_total = 0.0
    scenario_present = False
    for hid in hedge_ids:
        res = compute_mtm_for_hedge(
            db,
            hid,
            fx_symbol=fx_symbol,
            pricing_source=pricing_source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
        if res is None:
            continue
        total += res.mtm_value
        fx_rate_used = fx_rate_used or res.fx_rate
        if res.scenario_mtm_value is not None:
            scenario_present = True
            scenario_total += res.scenario_mtm_value
    return MtmComputation(
        mtm_value=total,
        fx_rate=fx_rate_used,
        scenario_mtm_value=scenario_total if scenario_present else None,
        price_used=None,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app import models

from app.services.lme_price_service import lme_price_by_day_prefer_types

AL_CASH_SETTLEMENT_SYMBOL = "P3Y00"  # LME Aluminium Cash Settlement (single source: LMEPrice)
AL_CASH_BID_SYMBOL = "ALUMINUM_CASH_BID"  # LME public (intraday) proxy only
AL_CASH_ASK_SYMBOL = "ALUMINUM_CASH_ASK"  # LME public (intraday) proxy only
AL_CASH_MID_SYMBOL = "ALUMINUM_CASH_MID"  # LME public (intraday) proxy only


@dataclass(frozen=True)
class ContractMtmResult:
    mtm_usd: float
    as_of_date: date
    methodology: str
    price_used: Optional[float] = None
    observation_start: Optional[date] = None
    observation_end_used: Optional[date] = None
    last_published_cash_date: Optional[date] = None


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # Accept ISO date or datetime
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            return None
    return None


def _month_bounds(month_name: str, year: int) -> Tuple[date, date]:
    # month_name comes from rfq_engine.MONTHS_EN; accept case-insensitive
    m = (month_name or "").strip().lower()
    months = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    if m not in months:
        raise ValueError("invalid month_name")
    month = months.index(m) + 1
    start = date(year, month, 1)
    # next month - 1 day
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _latest_cash_publish_date(db: Session) -> Optional[date]:
    """
    Returns the latest day we have an official Cash Settlement observation.

    Institutional rule (T5 MVP): settlement-derived values MUST use the authoritative
    settlement series only (no proxy fallbacks, no overrides).
    """
    q = (
        db.query(models.LMEPrice.ts_price)
        .filter(models.LMEPrice.symbol == AL_CASH_SETTLEMENT_SYMBOL)
        .filter(models.LMEPrice.price_type.in_(["close", "official"]))
        .order_by(models.LMEPrice.ts_price.desc(), models.LMEPrice.ts_ingest.desc())
    )
    row = q.first()
    return row[0].date() if row and row[0] else None


def _cash_price_by_day(
    db: Session,
    start: date,
    end: date,
) -> dict[date, float]:
    """
    Build a daily official Cash Settlement price series.

    Institutional rule (T5 MVP): do NOT fall back to intraday proxies.
    """
    # Institutional rule (T5 MVP): do NOT fall back to intraday proxies.
    # Only accept authoritative daily settlement types.
    series = lme_price_by_day_prefer_types(
        db,
        symbol=AL_CASH_SETTLEMENT_SYMBOL,
        start=start,
        end=end,
        price_types=["close", "official"],
    )
    return {d: float(p.price) for d, p in series.items()}


def compute_realized_avg_cash(
    db: Session,
    observation_start: date,
    observation_end: date,
    as_of_date: date,
) -> tuple[Optional[float], Optional[date], Optional[date]]:
    """
    Realized average for AVG/AVGInter:
    - Uses daily official Cash-Settlement when available (fallback to intraday proxies)
    - Up to the last published Cash settlement BEFORE as_of_date (i.e. excludes the current day)
    - Also capped by observation_end
    """
    last_published = _latest_cash_publish_date(db)
    if last_published is None:
        return None, None, None

    end_exclusive_today = as_of_date - timedelta(days=1)
    end_used = min(observation_end, last_published, end_exclusive_today)
    if end_used < observation_start:
        return None, None, last_published

    series = _cash_price_by_day(db, observation_start, end_used)
    points = [p for d, p in series.items() if observation_start <= d <= end_used]
    if not points:
        return None, end_used, last_published
    return float(sum(points) / len(points)), end_used, last_published


def compute_final_avg_cash(
    db: Session,
    observation_start: date,
    observation_end: date,
) -> tuple[Optional[float], Optional[date]]:
    """
    Final (full-period) average for AVG:
    - Uses daily official Cash-Settlement when available (fallback to intraday proxies)
    - Averages all available days in [observation_start, observation_end]
    - Returns (avg, last_published_cash_date)
    """
    last_published = _latest_cash_publish_date(db)
    if last_published is None:
        return None, None

    # We only consider published data; if we don't have through observation_end yet,
    # final average cannot be computed reliably.
    if last_published < observation_end:
        return None, last_published

    series = _cash_price_by_day(db, observation_start, observation_end)
    points = [p for d, p in series.items() if observation_start <= d <= observation_end]
    if not points:
        return None, last_published
    return float(sum(points) / len(points)), last_published


def _extract_avg_window_from_trade_specs(
    spec: dict[str, Any],
) -> tuple[Optional[date], Optional[date]]:
    """
    Derive observation window from the AVG/AVGInter leg in trade_specs.
    """
    for leg_key in ("leg1", "leg2"):
        leg = (spec or {}).get(leg_key) or {}
        pt = (leg.get("price_type") or "").strip()
        pt_norm = pt.lower()
        if pt_norm == "avg":
            month_name = leg.get("month_name")
            year = leg.get("year")
            if not month_name or year is None:
                continue
            try:
                return _month_bounds(str(month_name), int(year))
            except Exception:
                continue
        if pt_norm in {"avginter", "avg_inter", "avg inter"}:
            ss = _to_date(leg.get("start_date"))
            ee = _to_date(leg.get("end_date"))
            if ss and ee:
                return ss, ee
    return None, None


def _extract_fixed_price_and_side(
    trade_snapshot: dict[str, Any],
) -> tuple[Optional[float], Optional[str]]:
    legs = (trade_snapshot or {}).get("legs") or []
    for leg in legs:
        pt = (leg.get("price_type") or "").strip().lower()
        if pt == "fix":
            try:
                return float(leg.get("price")), str(leg.get("side") or "").lower()
            except Exception:
                return None, None
    # fallback: treat C2R as fixed if FIX not present
    for leg in legs:
        pt = (leg.get("price_type") or "").strip().lower()
        if pt == "c2r":
            try:
                return float(leg.get("price")), str(leg.get("side") or "").lower()
            except Exception:
                return None, None
    return None, None


def _extract_quantity_mt(
    trade_snapshot: dict[str, Any],
    rfq: Optional[models.Rfq],
) -> float:
    legs = (trade_snapshot or {}).get("legs") or []
    for leg in legs:
        vol = leg.get("volume_mt")
        if vol is not None:
            try:
                return float(vol)
            except Exception:
                pass
    if rfq and rfq.quantity_mt is not None:
        return float(rfq.quantity_mt)
    return 0.0


def compute_mtm_for_contract_avg(
    db: Session,
    contract: models.Contract,
    as_of_date: Optional[date] = None,
) -> Optional[ContractMtmResult]:
    """
    Implements the AVG rule from the user:
    - MTM for AVG/AVGInter uses realized average of Cash settlements from observation start
      up to the last published cash settlement (excludes current day).
    - The 3-month curve is NOT used for AVG unless explicitly referenced (not handled here).
    """
    # Institutional rule: MTM is only computed for active contracts.
    if getattr(contract, "status", None) != models.ContractStatus.active.value:
        return None

    as_of = as_of_date or date.today()
    rfq = db.get(models.Rfq, contract.rfq_id)
    idx = int(getattr(contract, "trade_index", None) or 0)
    spec = None
    if rfq and getattr(rfq, "trade_specs", None) and idx < len(rfq.trade_specs or []):
        spec = rfq.trade_specs[idx]
    if not isinstance(spec, dict):
        return None

    obs_start, obs_end = _extract_avg_window_from_trade_specs(spec)
    if not obs_start or not obs_end:
        return None

    fixed_price, fixed_side = _extract_fixed_price_and_side(contract.trade_snapshot or {})
    if fixed_price is None or fixed_side not in {"buy", "sell"}:
        return None

    qty = _extract_quantity_mt(contract.trade_snapshot or {}, rfq)
    if qty == 0.0:
        return None

    realized_avg, end_used, last_published = compute_realized_avg_cash(
        db,
        obs_start,
        obs_end,
        as_of_date=as_of,
    )
    if realized_avg is None:
        return None

    # Company payoff sign relative to fixed leg (mirrors rfq_engine expected payoff):
    # - If fixed leg is BUY: company receives when avg > fixed => (avg - fixed)
    # - If fixed leg is SELL: company pays when avg > fixed => (fixed - avg) == -(avg - fixed)
    sign = 1.0 if fixed_side == "buy" else -1.0
    mtm = (realized_avg - fixed_price) * qty * sign

    return ContractMtmResult(
        mtm_usd=float(mtm),
        as_of_date=as_of,
        methodology="contract.avg.realized_cash_settlement",
        price_used=float(realized_avg),
        observation_start=obs_start,
        observation_end_used=end_used,
        last_published_cash_date=last_published,
    )


def compute_settlement_value_for_contract_avg(
    db: Session,
    contract: models.Contract,
) -> Optional[ContractMtmResult]:
    """
    Settlement value for AVG/AVGInter at (or after) the settlement date:
    uses the full-period average of Cash settlements (monthly average).
    """
    # Institutional rule: MTM is only computed for active contracts.
    if getattr(contract, "status", None) != models.ContractStatus.active.value:
        return None

    rfq = db.get(models.Rfq, contract.rfq_id)
    idx = int(getattr(contract, "trade_index", None) or 0)
    spec = None
    if rfq and getattr(rfq, "trade_specs", None) and idx < len(rfq.trade_specs or []):
        spec = rfq.trade_specs[idx]
    if not isinstance(spec, dict):
        return None

    obs_start, obs_end = _extract_avg_window_from_trade_specs(spec)
    if not obs_start or not obs_end:
        return None

    fixed_price, fixed_side = _extract_fixed_price_and_side(contract.trade_snapshot or {})
    if fixed_price is None or fixed_side not in {"buy", "sell"}:
        return None

    qty = _extract_quantity_mt(contract.trade_snapshot or {}, rfq)
    if qty == 0.0:
        return None

    final_avg, last_published = compute_final_avg_cash(db, obs_start, obs_end)
    if final_avg is None:
        return None

    sign = 1.0 if fixed_side == "buy" else -1.0
    value = (final_avg - fixed_price) * qty * sign

    return ContractMtmResult(
        mtm_usd=float(value),
        as_of_date=date.today(),
        methodology="contract.avg.final_cash_settlement",
        price_used=float(final_avg),
        observation_start=obs_start,
        observation_end_used=obs_end,
        last_published_cash_date=last_published,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app import models
from app.services.contract_mtm_service import (
    AL_CASH_SETTLEMENT_SYMBOL,
    ContractMtmResult,
    compute_final_avg_cash,
    compute_mtm_for_contract_avg,
)


@dataclass(frozen=True)
class PnlUnrealizedResult:
    contract_id: str
    deal_id: int
    as_of_date: date
    unrealized_pnl_usd: float
    methodology: Optional[str]
    data_quality_flags: list[str]


@dataclass(frozen=True)
class PnlRealizedResult:
    contract_id: str
    deal_id: int
    settlement_date: date
    realized_pnl_usd: float
    methodology: Optional[str]
    data_quality_flags: list[str]
    locked_at: datetime
    source_hint: dict[str, Any] | None = None


def _deal_currency_flag(db: Session, deal_id: int) -> list[str]:
    deal = db.get(models.Deal, deal_id)
    if not deal:
        return ["missing_deal"]
    cur = (deal.currency or "").upper()
    if cur and cur != "USD":
        return ["currency_not_supported"]
    return []


def compute_unrealized_pnl_for_contract(
    db: Session,
    contract: models.Contract,
    *,
    as_of_date: date,
) -> PnlUnrealizedResult | None:
    """Unrealized P&L for active contracts only.

    Strict reuse of contract_mtm_service.
    """

    if getattr(contract, "status", None) != models.ContractStatus.active.value:
        return None

    flags: list[str] = []
    flags.extend(_deal_currency_flag(db, int(contract.deal_id)))

    res: ContractMtmResult | None = compute_mtm_for_contract_avg(
        db, contract, as_of_date=as_of_date
    )
    if res is None:
        flags.append("unrealized_not_available")
        return PnlUnrealizedResult(
            contract_id=str(contract.contract_id),
            deal_id=int(contract.deal_id),
            as_of_date=as_of_date,
            unrealized_pnl_usd=0.0,
            methodology=None,
            data_quality_flags=flags,
        )

    return PnlUnrealizedResult(
        contract_id=str(contract.contract_id),
        deal_id=int(contract.deal_id),
        as_of_date=as_of_date,
        unrealized_pnl_usd=float(res.mtm_usd),
        methodology=res.methodology,
        data_quality_flags=flags,
    )


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
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            return None
    return None


def _month_bounds(month_name: str, year: int) -> Tuple[date, date]:
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
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _extract_avg_window_from_trade_specs(
    spec: dict[str, Any],
) -> tuple[Optional[date], Optional[date]]:
    for leg_key in ("leg1", "leg2"):
        leg = (spec or {}).get(leg_key) or {}
        pt = (leg.get("price_type") or "").strip().lower()
        if pt == "avg":
            month_name = leg.get("month_name")
            year = leg.get("year")
            if not month_name or year is None:
                continue
            try:
                return _month_bounds(str(month_name), int(year))
            except Exception:
                continue
        if pt in {"avginter", "avg_inter", "avg inter"}:
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
    for leg in legs:
        pt = (leg.get("price_type") or "").strip().lower()
        if pt == "c2r":
            try:
                return float(leg.get("price")), str(leg.get("side") or "").lower()
            except Exception:
                return None, None
    return None, None


def _extract_quantity_mt(trade_snapshot: dict[str, Any], rfq: models.Rfq | None) -> float:
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


def compute_realized_pnl_for_contract(
    db: Session,
    contract: models.Contract,
) -> PnlRealizedResult | None:
    """Realized P&L (final settlement) for settled contracts only.

    This function intentionally does NOT call contract_mtm_service's settlement helper,
    because that helper is gated to active contracts by institutional rule.

    v1 supports AVG/AVGInter only and yields USD-only outputs.
    """

    if getattr(contract, "status", None) != models.ContractStatus.settled.value:
        return None

    if contract.settlement_date is None:
        return None

    flags: list[str] = []
    flags.extend(_deal_currency_flag(db, int(contract.deal_id)))

    rfq = db.get(models.Rfq, contract.rfq_id)
    if rfq is None or not isinstance(getattr(rfq, "trade_specs", None), list):
        flags.append("missing_trade_specs")
        return None

    idx = int(getattr(contract, "trade_index", None) or 0)
    if idx < 0 or idx >= len(rfq.trade_specs or []):
        flags.append("missing_trade_spec_index")
        return None

    spec = rfq.trade_specs[idx]
    if not isinstance(spec, dict):
        flags.append("missing_trade_spec")
        return None

    obs_start, obs_end = _extract_avg_window_from_trade_specs(spec)
    if not obs_start or not obs_end:
        flags.append("missing_observation_window")
        return None

    fixed_price, fixed_side = _extract_fixed_price_and_side(contract.trade_snapshot or {})
    if fixed_price is None or fixed_side not in {"buy", "sell"}:
        flags.append("missing_fixed_leg")
        return None

    qty = _extract_quantity_mt(contract.trade_snapshot or {}, rfq)
    if qty == 0.0:
        flags.append("missing_quantity")
        return None

    final_avg, last_published = compute_final_avg_cash(db, obs_start, obs_end)
    if final_avg is None:
        flags.append("final_not_available")
        return None

    sign = 1.0 if fixed_side == "buy" else -1.0
    value = (float(final_avg) - float(fixed_price)) * float(qty) * sign

    locked_at = datetime.now(timezone.utc)

    return PnlRealizedResult(
        contract_id=str(contract.contract_id),
        deal_id=int(contract.deal_id),
        settlement_date=contract.settlement_date,
        realized_pnl_usd=float(value),
        methodology="contract.avg.final_cash_settlement",
        data_quality_flags=flags,
        locked_at=locked_at,
        source_hint={
            "driver_symbol": AL_CASH_SETTLEMENT_SYMBOL,
            "cash_last_published_date": last_published.isoformat() if last_published else None,
            "observation_start": obs_start.isoformat(),
            "observation_end": obs_end.isoformat(),
        },
    )

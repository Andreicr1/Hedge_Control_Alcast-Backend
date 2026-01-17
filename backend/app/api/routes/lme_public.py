from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.services.lme_public import (
    fetch_lme_aluminum_dashboard_prices,
    fetch_lme_aluminum_intraday_snapshot,
    snapshot_as_of_datetime_utc,
)

router = APIRouter(prefix="/market-data/lme", tags=["market_data_lme"])


@router.get(
    "/aluminum/intraday",
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
async def get_aluminum_intraday(headless: bool = True):
    try:
        snap = await fetch_lme_aluminum_intraday_snapshot(headless=headless)
        return {
            "as_of_date": snap.as_of_date.isoformat(),
            "currency": snap.currency,
            "quotes": [
                {
                    "contract": r.contract,
                    "bid_qty_lots": r.bid_qty_lots,
                    "bid": float(r.bid) if r.bid is not None else None,
                    "ask": float(r.ask) if r.ask is not None else None,
                    "ask_qty_lots": r.ask_qty_lots,
                }
                for r in snap.quotes
            ],
            "last_traded": [
                {
                    "contract": r.contract,
                    "last_price": float(r.last_price) if r.last_price is not None else None,
                    "pct_change": float(r.pct_change) if r.pct_change is not None else None,
                    "abs_change": float(r.abs_change) if r.abs_change is not None else None,
                    "last_trade_time_utc": r.last_trade_time_utc,
                    "prev_close": float(r.prev_close) if r.prev_close is not None else None,
                }
                for r in snap.last_traded
            ],
            "raw": snap.raw,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao buscar intraday público da LME: {exc}"
        )


@router.post(
    "/aluminum/ingest",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
async def ingest_aluminum_intraday(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
    headless: bool = True,
):
    """
    Ingest an LME public (15-min delayed / day-delayed published) snapshot into market_prices.

    Mapping:
    - ALUMINUM_3M_LAST: "3-month" last traded price (Intraday tab)
    - ALUMINUM_CASH_BID / ALUMINUM_CASH_ASK: Cash bid/offer (Trading summary tab)
    - ALUMINUM: alias to ALUMINUM_3M_LAST (for charting)
    - ALUMINUM_BID / ALUMINUM_ASK: aliases to CASH bid/ask (for existing /market/aluminum/quote behavior)
    """
    # Use a combined fetch to ensure we store Cash + 3M last consistently.
    prices = await fetch_lme_aluminum_dashboard_prices(headless=headless)

    # Build a conservative as_of from intraday snapshot time for 3M last (if available)
    snap = await fetch_lme_aluminum_intraday_snapshot(headless=headless)
    as_of = snapshot_as_of_datetime_utc(snap)

    cash_bid = float(prices.cash_bid)
    cash_ask = float(prices.cash_ask)
    three_month_last = float(prices.three_month_last)
    cash_mid = float((cash_bid + cash_ask) / 2.0)

    def _store(symbol: str, price: float):
        mp = models.MarketPrice(
            source="lme-public",
            symbol=symbol,
            contract_month=None,
            price=price,
            currency="USD",
            as_of=as_of,
            fx=False,
        )
        db.add(mp)

    _store("ALUMINUM_CASH_BID", cash_bid)
    _store("ALUMINUM_CASH_ASK", cash_ask)
    # Daily cash "settlement-like" reference for realized average calculations (mid of official bid/offer).
    _store("ALUMINUM_CASH_MID", cash_mid)
    _store("ALUMINUM_3M_LAST", three_month_last)

    # Compatibility / existing consumers
    _store("ALUMINUM", three_month_last)
    _store("ALUMINUM_BID", cash_bid)
    _store("ALUMINUM_ASK", cash_ask)

    db.commit()

    return {
        "as_of": as_of.isoformat(),
        "stored": [
            "ALUMINUM_CASH_BID",
            "ALUMINUM_CASH_ASK",
            "ALUMINUM_CASH_MID",
            "ALUMINUM_3M_LAST",
            "ALUMINUM",
            "ALUMINUM_BID",
            "ALUMINUM_ASK",
        ],
        "cash_bid": cash_bid,
        "cash_ask": cash_ask,
        "cash_mid": cash_mid,
        "three_month_last": three_month_last,
    }

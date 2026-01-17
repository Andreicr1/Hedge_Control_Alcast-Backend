from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.aluminum import AluminumHistoryPointRead, AluminumQuoteRead

router = APIRouter(prefix="/market/aluminum", tags=["market_aluminum"])

# Recommended ingestion convention:
# - ALUMINUM_BID (USD/ton)
# - ALUMINUM_ASK (USD/ton)
# Optional fallback:
# - ALUMINUM (mid)
# - ALUMINUM_CASH_SETTLEMENT (from Westmetall scheduler)
AL_BID_SYMBOL = "ALUMINUM_BID"
AL_ASK_SYMBOL = "ALUMINUM_ASK"
AL_MID_SYMBOL = "ALUMINUM"
# Westmetall symbols (used by scheduler)
AL_CASH_SETTLEMENT = "ALUMINUM_CASH_SETTLEMENT"
AL_3M_SETTLEMENT = "ALUMINUM_3M_SETTLEMENT"


def _latest_price(db: Session, symbol: str) -> Optional[models.MarketPrice]:
    return (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.symbol == symbol)
        .order_by(models.MarketPrice.as_of.desc(), models.MarketPrice.created_at.desc())
        .first()
    )


@router.get(
    "/quote",
    response_model=AluminumQuoteRead,
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def get_aluminum_quote(db: Session = Depends(get_db)):
    bid = _latest_price(db, AL_BID_SYMBOL)
    ask = _latest_price(db, AL_ASK_SYMBOL)
    mid = _latest_price(db, AL_MID_SYMBOL)

    # Fallback to Westmetall Cash Settlement if LME data not available
    cash_settlement = _latest_price(db, AL_CASH_SETTLEMENT)

    # Fallback priority: LME BID/ASK > LME MID > Westmetall CASH_SETTLEMENT
    if not bid and mid:
        bid = mid
    if not ask and mid:
        ask = mid
    if not bid and cash_settlement:
        bid = cash_settlement
    if not ask and cash_settlement:
        ask = cash_settlement

    if not bid or not ask:
        raise HTTPException(status_code=404, detail="No aluminum market data found")

    as_of = max(bid.as_of, ask.as_of)
    source = bid.source if bid.as_of >= ask.as_of else ask.source
    currency = bid.currency or ask.currency or "USD"

    return AluminumQuoteRead(
        bid=bid.price,
        ask=ask.price,
        currency=currency,
        unit="ton",
        as_of=as_of,
        source=source,
    )


@router.get(
    "/history",
    response_model=List[AluminumHistoryPointRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def get_aluminum_history(
    range: Literal["7d", "30d", "1y"] = Query("30d"),
    db: Session = Depends(get_db),
):
    days = 7 if range == "7d" else 30 if range == "30d" else 365
    start = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(models.MarketPrice)
        .filter(
            models.MarketPrice.symbol.in_(
                [
                    AL_BID_SYMBOL,
                    AL_ASK_SYMBOL,
                    AL_MID_SYMBOL,
                    AL_CASH_SETTLEMENT,
                    AL_3M_SETTLEMENT,  # Include Westmetall symbols
                ]
            )
        )
        .filter(models.MarketPrice.as_of >= start)
        .order_by(models.MarketPrice.as_of.asc(), models.MarketPrice.created_at.asc())
        .limit(10000)
        .all()
    )

    # Bucket by day (UTC) and take the last observation per symbol on that day.
    by_day: Dict[str, Dict[str, models.MarketPrice]] = {}
    for r in rows:
        day_key = r.as_of.astimezone(timezone.utc).date().isoformat()
        by_day.setdefault(day_key, {})
        by_day[day_key][r.symbol] = r

    points: List[AluminumHistoryPointRead] = []
    for day_key in sorted(by_day.keys()):
        bucket = by_day[day_key]
        bid = bucket.get(AL_BID_SYMBOL)
        ask = bucket.get(AL_ASK_SYMBOL)
        mid = bucket.get(AL_MID_SYMBOL)
        cash = bucket.get(AL_CASH_SETTLEMENT)  # Westmetall fallback

        # Priority: LME BID/ASK > LME MID > Westmetall CASH_SETTLEMENT
        if bid and ask:
            ts = max(bid.as_of, ask.as_of)
            mid_value = (bid.price + ask.price) / 2.0
            points.append(
                AluminumHistoryPointRead(ts=ts, mid=mid_value, bid=bid.price, ask=ask.price)
            )
        elif mid:
            points.append(AluminumHistoryPointRead(ts=mid.as_of, mid=mid.price))
        elif cash:
            # Use Westmetall cash settlement as mid price
            points.append(AluminumHistoryPointRead(ts=cash.as_of, mid=cash.price))
        elif bid and not ask:
            points.append(AluminumHistoryPointRead(ts=bid.as_of, mid=bid.price, bid=bid.price))
        elif ask and not bid:
            points.append(AluminumHistoryPointRead(ts=ask.as_of, mid=ask.price, ask=ask.price))

    return points

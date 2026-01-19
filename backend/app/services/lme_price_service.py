from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class LMEPricePick:
    price: float
    ts_price: datetime
    price_type: str
    source: str


def _as_of_end_dt(as_of: date) -> datetime:
    return datetime.combine(as_of, time(23, 59, 59), tzinfo=timezone.utc)


def latest_lme_price_prefer_types(
    db: Session,
    *,
    symbol: str,
    as_of: date,
    price_types: Iterable[str],
    market: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[models.LMEPrice]:
    cutoff = _as_of_end_dt(as_of)

    for pt in list(price_types):
        q = db.query(models.LMEPrice).filter(models.LMEPrice.symbol == symbol)
        q = q.filter(models.LMEPrice.ts_price <= cutoff)
        q = q.filter(models.LMEPrice.price_type == str(pt))
        if market:
            q = q.filter(models.LMEPrice.market == market)
        if source:
            q = q.filter(models.LMEPrice.source == source)
        row = q.order_by(models.LMEPrice.ts_price.desc(), models.LMEPrice.ts_ingest.desc()).first()
        if row is not None:
            return row

    return None


def lme_price_by_day_prefer_types(
    db: Session,
    *,
    symbol: str,
    start: date,
    end: date,
    price_types: list[str],
    market: Optional[str] = None,
    source: Optional[str] = None,
) -> dict[date, LMEPricePick]:
    if end < start:
        return {}

    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    q = db.query(models.LMEPrice).filter(models.LMEPrice.symbol == symbol)
    q = q.filter(models.LMEPrice.ts_price >= start_dt)
    q = q.filter(models.LMEPrice.ts_price < end_dt)
    if price_types:
        q = q.filter(models.LMEPrice.price_type.in_(list(price_types)))
    if market:
        q = q.filter(models.LMEPrice.market == market)
    if source:
        q = q.filter(models.LMEPrice.source == source)

    rows = (
        q.order_by(models.LMEPrice.ts_price.asc(), models.LMEPrice.ts_ingest.asc())
        .all()
    )

    # Track latest obs per (day, price_type)
    latest_by_day_type: dict[tuple[date, str], models.LMEPrice] = {}
    for r in rows:
        day = r.ts_price.date()
        key = (day, str(r.price_type))
        prev = latest_by_day_type.get(key)
        if prev is None:
            latest_by_day_type[key] = r
            continue
        if (r.ts_price, r.ts_ingest) >= (prev.ts_price, prev.ts_ingest):
            latest_by_day_type[key] = r

    out: dict[date, LMEPricePick] = {}
    day = start
    while day <= end:
        picked: Optional[models.LMEPrice] = None
        picked_type: Optional[str] = None
        for pt in price_types:
            candidate = latest_by_day_type.get((day, str(pt)))
            if candidate is not None:
                picked = candidate
                picked_type = str(pt)
                break
        if picked is not None and picked_type is not None:
            out[day] = LMEPricePick(
                price=float(picked.price),
                ts_price=picked.ts_price,
                price_type=picked_type,
                source=str(picked.source),
            )
        day = day + timedelta(days=1)

    return out

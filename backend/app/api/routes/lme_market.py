from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_ingest_token
from app.database import get_db
from app.models.lme_price import LMEPrice
from app.schemas.lme import LMEPriceIngest

router = APIRouter(tags=["lme_market"])  # no prefix; paths are specified explicitly


_SYMBOLS = {
    "P3Y00": {"name": "Aluminium Hg Cash", "price_types": {"live", "close"}},
    "P4Y00": {"name": "Aluminium Hg 3M", "price_types": {"live", "close"}},
    "Q7Y00": {"name": "Aluminium Hg Official", "price_types": {"official"}},
    "^USDBRL": {"name": "U.S. Dollar/Brazilian Real", "price_types": {"live", "close"}},
}


def _latest(db: Session, symbol: str, price_type: str) -> LMEPrice | None:
    return (
        db.query(LMEPrice)
        .filter(LMEPrice.symbol == symbol)
        .filter(LMEPrice.price_type == price_type)
        .order_by(LMEPrice.ts_price.desc(), LMEPrice.ts_ingest.desc())
        .first()
    )


@router.post(
    "/ingest/lme/price",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingest_token)],
)
def ingest_lme_price(payload: LMEPriceIngest, db: Session = Depends(get_db)) -> Dict:
    spec = _SYMBOLS.get(payload.symbol)
    if not spec:
        raise HTTPException(status_code=400, detail="Unsupported symbol")
    if payload.price_type not in spec["price_types"]:
        raise HTTPException(status_code=400, detail="price_type mismatch for symbol")

    record = LMEPrice(
        symbol=payload.symbol,
        name=payload.name,
        market=payload.market,
        price=float(payload.price),
        price_type=payload.price_type,
        ts_price=payload.ts_price,
        source=payload.source,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "symbol": record.symbol,
        "price": float(record.price),
        "price_type": record.price_type,
        "ts_price": record.ts_price.isoformat(),
        "ts_ingest": record.ts_ingest.isoformat() if record.ts_ingest else None,
        "source": record.source,
    }


@router.get("/market/lme/aluminum/live")
def get_lme_aluminum_live(db: Session = Depends(get_db)) -> Dict:
    cash = _latest(db, "P3Y00", "live")
    three_month = _latest(db, "P4Y00", "live")

    def _leg(symbol: str, row: LMEPrice | None) -> Dict:
        if not row:
            return {"symbol": symbol, "price": None, "ts": None}
        return {
            "symbol": row.symbol,
            "price": float(row.price),
            "ts": row.ts_price.astimezone(timezone.utc).isoformat(),
        }

    return {
        "cash": _leg("P3Y00", cash),
        "three_month": _leg("P4Y00", three_month),
    }


def _history_daily(db: Session, symbol: str, price_type: str) -> List[Dict]:
    # Fixed, stable behavior: return last 365 days, bucketed by UTC date.
    start = datetime.now(timezone.utc) - timedelta(days=365)

    rows = (
        db.query(LMEPrice)
        .filter(LMEPrice.symbol == symbol)
        .filter(LMEPrice.price_type == price_type)
        .filter(LMEPrice.ts_price >= start)
        .order_by(LMEPrice.ts_price.asc(), LMEPrice.ts_ingest.asc())
        .limit(20000)
        .all()
    )

    by_day: Dict[str, LMEPrice] = {}
    for r in rows:
        day_key = r.ts_price.astimezone(timezone.utc).date().isoformat()
        by_day[day_key] = r  # last wins due to ordering

    out: List[Dict] = []
    for day_key in sorted(by_day.keys()):
        r = by_day[day_key]
        out.append({"date": day_key, "price": float(r.price)})
    return out


@router.get("/market/lme/aluminum/history/cash")
def get_lme_aluminum_history_cash(db: Session = Depends(get_db)) -> List[Dict]:
    # Prefer Cash close (P3Y00 close) if available.
    # Otherwise, fall back to Q7Y00 official closes (CashHistorical sheets used for D-1 MTM).
    data = _history_daily(db, "P3Y00", "close")
    if data:
        return data
    return _history_daily(db, "Q7Y00", "official")


@router.get("/market/lme/aluminum/history/3m")
def get_lme_aluminum_history_3m(db: Session = Depends(get_db)) -> List[Dict]:
    # Prefer close series for chart/MTM; fall back to live if close isn't available.
    data = _history_daily(db, "P4Y00", "close")
    if data:
        return data
    return _history_daily(db, "P4Y00", "live")


@router.get("/market/lme/aluminum/official/latest")
def get_lme_aluminum_official_latest(db: Session = Depends(get_db)) -> Dict:
    row = _latest(db, "Q7Y00", "official")
    if not row:
        raise HTTPException(status_code=404, detail="Missing official LME aluminum price")

    ts_utc = row.ts_price.astimezone(timezone.utc)
    return {
        "symbol": row.symbol,
        "price": float(row.price),
        "ts": ts_utc.isoformat(),
        "date": ts_utc.date().isoformat(),
    }

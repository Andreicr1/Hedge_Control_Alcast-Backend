from datetime import datetime
from typing import List, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import MarketPriceCreate, MarketPriceRead
from app.services.audit import audit_event

router = APIRouter(prefix="/market-data", tags=["market_data"])


@router.post("", response_model=MarketPriceRead, status_code=status.HTTP_201_CREATED)
def create_market_price(
    payload: MarketPriceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    record = models.MarketPrice(
        source=payload.source,
        symbol=payload.symbol,
        contract_month=payload.contract_month,
        price=payload.price,
        currency=payload.currency,
        as_of=payload.as_of,
        fx=payload.fx,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    audit_event(
        "market_price.created",
        current_user.id,
        {"market_price_id": record.id, "symbol": record.symbol, "source": record.source},
    )
    return record


@router.get(
    "",
    response_model=List[MarketPriceRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def list_market_prices(
    db: Session = Depends(get_db),
    symbol: Optional[str] = None,
    contract_month: Optional[str] = None,
    source: Optional[str] = None,
    fx_only: bool = False,
    latest: bool = Query(False, description="Return only the latest matching price"),
):
    query = db.query(models.MarketPrice)
    if symbol:
        query = query.filter(models.MarketPrice.symbol == symbol)
    if contract_month:
        query = query.filter(models.MarketPrice.contract_month == contract_month)
    if source:
        query = query.filter(models.MarketPrice.source == source)
    if fx_only:
        query = query.filter(models.MarketPrice.fx.is_(True))
    query = query.order_by(models.MarketPrice.as_of.desc(), models.MarketPrice.created_at.desc())
    if latest:
        record = query.first()
        return [record] if record else []
    return query.limit(200).all()


def _ingest_from_yahoo(
    symbols: List[str],
    db: Session,
    current_user: models.User,
    pricing_source: Optional[str] = None,
    fx_only: bool = False,
) -> List[models.MarketPrice]:
    results: List[models.MarketPrice] = []
    for symbol in symbols:
        if fx_only and not symbol.endswith("=X"):
            raise HTTPException(status_code=400, detail=f"{symbol} is not an FX symbol (=X)")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get("regularMarketPrice")
            currency = info.get("currency") or "USD"
            if price is None:
                raise ValueError("No market price")
            source_name = pricing_source or "yahoo"
            mp = models.MarketPrice(
                source=source_name,
                symbol=symbol,
                contract_month=None,
                price=price,
                currency=currency,
                as_of=datetime.utcnow(),
                fx=symbol.endswith("=X") or fx_only,
            )
            db.add(mp)
            db.commit()
            db.refresh(mp)
            results.append(mp)
            audit_event(
                "market_price.yahoo_ingest",
                current_user.id,
                {
                    "symbol": symbol,
                    "price": price,
                    "currency": currency,
                    "fx": mp.fx,
                    "source": source_name,
                },
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to fetch {symbol}: {exc}")

    return results


@router.post(
    "/yahoo",
    response_model=List[MarketPriceRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def fetch_from_yahoo(
    symbols: List[str] = Query(..., description="Symbols to fetch, e.g. LMEALI=LX,USDBRL=X"),
    pricing_source: Optional[str] = Query(
        None, description="Optional pricing source label to store"
    ),
    fx_only: bool = Query(False, description="If true, only fetch FX symbols (=X) and flag as fx"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    return _ingest_from_yahoo(
        symbols, db, current_user, pricing_source=pricing_source, fx_only=fx_only
    )


@router.post(
    "/fx",
    response_model=List[MarketPriceRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def fetch_fx_from_yahoo(
    symbols: List[str] = Query(..., description="FX symbols (e.g. USDBRL=X, EURUSD=X)"),
    pricing_source: Optional[str] = Query(
        None, description="Optional pricing source label to store"
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    return _ingest_from_yahoo(
        symbols, db, current_user, pricing_source=pricing_source, fx_only=True
    )

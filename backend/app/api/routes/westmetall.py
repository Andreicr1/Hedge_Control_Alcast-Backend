from __future__ import annotations

from datetime import date
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.services.westmetall import as_of_datetime_utc, fetch_westmetall_daily_rows

router = APIRouter(prefix="/market-data/westmetall", tags=["market_data_westmetall"])


@router.post(
    "/aluminum/cash-settlement/ingest",
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def ingest_aluminum_cash_settlement(
    year: int | None = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ingest Westmetall "LME Aluminium Cash-Settlement" daily series into market_prices.

    This is the authoritative series for AVG/Monthly Average contracts in this system.
    Source pages:
    - Daily table: https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash
    - Monthly average: https://www.westmetall.com/en/markdaten.php?action=averages&field=LME_Al_cash

    Stored symbols:
    - ALUMINUM_CASH_SETTLEMENT: daily official Cash-Settlement (USD/ton)
    - ALUMINUM_3M_SETTLEMENT: daily official 3-month settlement (USD/ton) [optional, not used for AVG]
    """
    y = int(year or date.today().year)
    try:
        rows = fetch_westmetall_daily_rows(y)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao buscar Westmetall: {exc}")

    inserted = 0
    skipped = 0

    for r in rows:
        if r.cash_settlement is None:
            continue
        as_of = as_of_datetime_utc(r.as_of_date)

        exists = (
            db.query(models.MarketPrice.id)
            .filter(models.MarketPrice.source == "westmetall")
            .filter(models.MarketPrice.symbol == "ALUMINUM_CASH_SETTLEMENT")
            .filter(models.MarketPrice.as_of == as_of)
            .first()
        )
        if exists:
            skipped += 1
            continue

        db.add(
            models.MarketPrice(
                source="westmetall",
                symbol="ALUMINUM_CASH_SETTLEMENT",
                contract_month=None,
                price=float(r.cash_settlement),
                currency="USD",
                as_of=as_of,
                fx=False,
            )
        )
        inserted += 1

        # Store 3M settlement too, if available (for completeness / future use).
        if r.three_month_settlement is not None:
            exists_3m = (
                db.query(models.MarketPrice.id)
                .filter(models.MarketPrice.source == "westmetall")
                .filter(models.MarketPrice.symbol == "ALUMINUM_3M_SETTLEMENT")
                .filter(models.MarketPrice.as_of == as_of)
                .first()
            )
            if not exists_3m:
                db.add(
                    models.MarketPrice(
                        source="westmetall",
                        symbol="ALUMINUM_3M_SETTLEMENT",
                        contract_month=None,
                        price=float(r.three_month_settlement),
                        currency="USD",
                        as_of=as_of,
                        fx=False,
                    )
                )

    db.commit()

    return {
        "year": y,
        "inserted": inserted,
        "skipped": skipped,
        "source": "westmetall",
        "symbols": ["ALUMINUM_CASH_SETTLEMENT", "ALUMINUM_3M_SETTLEMENT"],
    }

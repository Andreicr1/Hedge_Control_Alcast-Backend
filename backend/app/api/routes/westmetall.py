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
    Ingest Westmetall "LME Aluminium Cash-Settlement" daily series into lme_prices.

    This is the authoritative series for AVG/Monthly Average contracts in this system.
    Source pages:
    - Daily table: https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash
    - Monthly average: https://www.westmetall.com/en/markdaten.php?action=averages&field=LME_Al_cash

    Stored symbols (single source: LMEPrice):
    - P3Y00: daily Cash settlement (USD/ton)
    - P4Y00: daily 3-month settlement (USD/ton) [optional, not used for AVG]
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
            db.query(models.LMEPrice.id)
            .filter(models.LMEPrice.source == "westmetall")
            .filter(models.LMEPrice.symbol == "P3Y00")
            .filter(models.LMEPrice.ts_price == as_of)
            .first()
        )
        if exists:
            skipped += 1
            continue

        db.add(
            models.LMEPrice(
                symbol="P3Y00",
                name="LME Aluminium Cash Settlement",
                market="LME",
                price=float(r.cash_settlement),
                price_type="close",
                ts_price=as_of,
                source="westmetall",
            )
        )
        inserted += 1

        # Store 3M settlement too, if available (for completeness / future use).
        if r.three_month_settlement is not None:
            exists_3m = (
                db.query(models.LMEPrice.id)
                .filter(models.LMEPrice.source == "westmetall")
                .filter(models.LMEPrice.symbol == "P4Y00")
                .filter(models.LMEPrice.ts_price == as_of)
                .first()
            )
            if not exists_3m:
                db.add(
                    models.LMEPrice(
                        symbol="P4Y00",
                        name="LME Aluminium 3M Settlement",
                        market="LME",
                        price=float(r.three_month_settlement),
                        price_type="close",
                        ts_price=as_of,
                        source="westmetall",
                    )
                )

    db.commit()

    return {
        "year": y,
        "inserted": inserted,
        "skipped": skipped,
        "source": "westmetall",
        "symbols": ["P3Y00", "P4Y00"],
    }

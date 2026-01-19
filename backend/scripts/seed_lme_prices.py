from __future__ import annotations

import argparse
import math
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.lme_price import LMEPrice


_SYMBOL_SPECS: dict[str, dict[str, str]] = {
    "P3Y00": {"name": "Aluminium Hg Cash", "market": "LME"},
    "P4Y00": {"name": "Aluminium Hg 3M", "market": "LME"},
    "Q7Y00": {"name": "Aluminium Hg Official", "market": "LME"},
}


def _generate_price(base: float, day_index: int) -> float:
    # Deterministic pseudo-series: gentle seasonality + small drift.
    wave = 35.0 * math.sin(day_index / 9.0)
    drift = 0.6 * day_index
    return round(base + wave + drift, 2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seeds demo LME prices into the configured DATABASE_URL. "
            "This is intended for local/dev environments to validate charts and endpoints."
        )
    )
    parser.add_argument("--days", type=int, default=120, help="How many days of close data")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert even if lme_prices already has data (may create duplicates)",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow running even when ENVIRONMENT=production/prod",
    )
    args = parser.parse_args()

    environment = str(os.getenv("ENVIRONMENT", "dev") or "dev").strip().lower()
    if environment in {"prod", "production"} and not args.allow_production:
        raise SystemExit(
            "Refusing to seed when ENVIRONMENT=production. "
            "Re-run with --allow-production if you really intend to do this."
        )

    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=args.days)).date()

    db = SessionLocal()
    try:
        existing = int(db.query(func.count(LMEPrice.id)).scalar() or 0)
        if existing > 0 and not args.force:
            print(f"lme_prices already has {existing} row(s); skipping (use --force to insert anyway)")
            return 0

        to_add: list[LMEPrice] = []

        # Daily close series for chart endpoints.
        for i in range(args.days):
            day = start_day + timedelta(days=i)
            # Use a fixed timestamp per day (16:00 UTC) so bucketing is stable.
            ts_close = datetime(day.year, day.month, day.day, 16, 0, 0, tzinfo=timezone.utc)

            to_add.append(
                LMEPrice(
                    symbol="P3Y00",
                    name=_SYMBOL_SPECS["P3Y00"]["name"],
                    market=_SYMBOL_SPECS["P3Y00"]["market"],
                    price=_generate_price(2250.0, i),
                    price_type="close",
                    ts_price=ts_close,
                    source="seed_script",
                )
            )
            to_add.append(
                LMEPrice(
                    symbol="P4Y00",
                    name=_SYMBOL_SPECS["P4Y00"]["name"],
                    market=_SYMBOL_SPECS["P4Y00"]["market"],
                    price=_generate_price(2310.0, i),
                    price_type="close",
                    ts_price=ts_close,
                    source="seed_script",
                )
            )
            # Add official series as well (used as a fallback for cash).
            to_add.append(
                LMEPrice(
                    symbol="Q7Y00",
                    name=_SYMBOL_SPECS["Q7Y00"]["name"],
                    market=_SYMBOL_SPECS["Q7Y00"]["market"],
                    price=_generate_price(2235.0, i),
                    price_type="official",
                    ts_price=ts_close,
                    source="seed_script",
                )
            )

        # Latest live legs for the live widget.
        to_add.append(
            LMEPrice(
                symbol="P3Y00",
                name=_SYMBOL_SPECS["P3Y00"]["name"],
                market=_SYMBOL_SPECS["P3Y00"]["market"],
                price=_generate_price(2265.0, args.days),
                price_type="live",
                ts_price=now,
                source="seed_script",
            )
        )
        to_add.append(
            LMEPrice(
                symbol="P4Y00",
                name=_SYMBOL_SPECS["P4Y00"]["name"],
                market=_SYMBOL_SPECS["P4Y00"]["market"],
                price=_generate_price(2325.0, args.days),
                price_type="live",
                ts_price=now,
                source="seed_script",
            )
        )

        db.add_all(to_add)
        db.commit()

        inserted = len(to_add)
        total = int(db.query(func.count(LMEPrice.id)).scalar() or 0)
        print(f"Inserted {inserted} row(s). lme_prices now has {total} row(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

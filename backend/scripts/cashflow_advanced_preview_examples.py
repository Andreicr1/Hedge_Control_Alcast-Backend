from __future__ import annotations

import json
from datetime import datetime
import logging
import os
from pathlib import Path
import sys

# Keep example output stable/clean (avoid INFO request logs from app/main.py).
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Allow running this script directly (python scripts/...) while importing `app.*`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# Avoid requiring Postgres drivers when generating docs/examples.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.api import deps
from app.models.domain import RoleName

# Reuse the deterministic in-memory setup from the test module so the examples
# are guaranteed to match actual API output.
from tests.test_cashflow_advanced_preview import (  # noqa: E402
    TestingSessionLocal,
    _seed_avg_contract_with_pnl,
    _stub_user,
    app,
    client,
)


def _pretty(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def main() -> None:
    _seed_avg_contract_with_pnl()

    # Example 1: USD-only
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    r_usd = client.post(
        "/cashflow/advanced/preview",
        json={
            "as_of": "2025-01-10",
            "assumptions": {"forward_price_assumption": 120.0},
        },
    )
    r_usd.raise_for_status()

    print("=== REQUEST (USD-only) ===")
    print(
        _pretty(
            {
                "as_of": "2025-01-10",
                "assumptions": {"forward_price_assumption": 120.0},
            }
        )
    )
    print("=== RESPONSE (USD-only) ===")
    print(_pretty(r_usd.json()))

    # Example 2: BRL reporting with explicit FX
    db = TestingSessionLocal()
    try:
        from app import models

        db.add(
            models.MarketPrice(
                source="yahoo",
                symbol="^USDBRL",
                price=5.0,
                currency="BRL",
                as_of=datetime.fromisoformat("2025-01-09T00:00:00"),
                fx=True,
            )
        )
        db.commit()
    finally:
        db.close()

    r_brl = client.post(
        "/cashflow/advanced/preview",
        json={
            "as_of": "2025-01-10",
            "reporting": {
                "reporting_currency": "BRL",
                "fx": {
                    "mode": "explicit",
                    "fx_symbol": "^USDBRL",
                    "fx_source": "barchart_excel_usdbrl",
                },
            },
            "assumptions": {"forward_price_assumption": 120.0},
        },
    )
    r_brl.raise_for_status()

    print("=== REQUEST (BRL + explicit FX) ===")
    print(
        _pretty(
            {
                "as_of": "2025-01-10",
                "reporting": {
                    "reporting_currency": "BRL",
                    "fx": {
                        "mode": "explicit",
                        "fx_symbol": "^USDBRL",
                        "fx_source": "yahoo",
                    },
                },
                "assumptions": {"forward_price_assumption": 120.0},
            }
        )
    )
    print("=== RESPONSE (BRL + explicit FX) ===")
    print(_pretty(r_brl.json()))


if __name__ == "__main__":
    main()

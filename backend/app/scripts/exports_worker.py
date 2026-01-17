from __future__ import annotations

import argparse
import time

from app.database import SessionLocal
from app.services.exports_worker import run_once


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal exports worker (queued -> running -> done|failed)"
    )
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--interval-seconds", type=float, default=1.0, help="Sleep between polls")
    args = parser.parse_args()

    if args.once:
        with SessionLocal() as db:
            processed = run_once(db)
        return 0 if processed else 2

    while True:
        with SessionLocal() as db:
            processed = run_once(db)
        if not processed:
            time.sleep(max(0.1, float(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())

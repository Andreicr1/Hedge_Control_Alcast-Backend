from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import models
from app.database import SessionLocal
from app.services.westmetall import as_of_datetime_utc, fetch_westmetall_daily_rows
from app.services.finance_pipeline_daily import execute_finance_pipeline_daily

logger = logging.getLogger("alcast.scheduler")


DEFAULT_DAILY_UTC_HOUR = 9  # 09:00 GMT/UTC
DEFAULT_FINANCE_PIPELINE_UTC_HOUR = 10  # 10:00 GMT/UTC


@dataclass(frozen=True)
class JobResult:
    year: int
    inserted: int
    skipped: int


def _try_pg_advisory_lock(db, key: int) -> bool:
    """
    Best-effort distributed lock for Postgres. On other DBs, returns True (no-op).
    """
    try:
        dialect = db.get_bind().dialect.name  # type: ignore[attr-defined]
    except Exception:
        return True
    if dialect != "postgresql":
        return True
    try:
        locked = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": int(key)}).scalar()
        return bool(locked)
    except Exception:
        # If lock fails, don't block the job forever; just proceed.
        return True


def _unlock_pg_advisory_lock(db, key: int) -> None:
    try:
        dialect = db.get_bind().dialect.name  # type: ignore[attr-defined]
    except Exception:
        return
    if dialect != "postgresql":
        return
    try:
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(key)})
    except Exception:
        return


def ingest_westmetall_cash_settlement_for_year(year: int) -> JobResult:
    """
    Same logic as the API route, but callable from a background job.
    Inserts only missing rows (dedupe by source+symbol+as_of).
    """
    rows = fetch_westmetall_daily_rows(int(year))
    inserted = 0
    skipped = 0

    db = SessionLocal()
    lock_key = 912025  # stable key for this scheduled job
    got_lock = _try_pg_advisory_lock(db, lock_key)
    if not got_lock:
        logger.info("westmetall_ingest_skipped_locked", extra={"year": int(year)})
        db.close()
        return JobResult(year=int(year), inserted=0, skipped=0)

    try:
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
        return JobResult(year=int(year), inserted=inserted, skipped=skipped)
    finally:
        _unlock_pg_advisory_lock(db, lock_key)
        db.close()


class DailyJobRunner:
    """
    Minimal dependency-free daily scheduler.
    NOTE: In multi-worker setups, each worker will start this thread.
    We mitigate duplicates via a Postgres advisory lock.
    """

    def __init__(self, hour_utc: int = DEFAULT_DAILY_UTC_HOUR) -> None:
        self.hour_utc = int(hour_utc)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-job-runner", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=self.hour_utc, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run + timedelta(days=1)

            wait_s = max(0.0, (next_run - now).total_seconds())
            logger.info(
                "scheduler_wait",
                extra={"next_run_utc": next_run.isoformat(), "wait_seconds": int(wait_s)},
            )
            if self._stop.wait(wait_s):
                break

            # Run job
            try:
                y = datetime.now(timezone.utc).year
                res = ingest_westmetall_cash_settlement_for_year(y)
                logger.info(
                    "westmetall_ingest_ok",
                    extra={"year": res.year, "inserted": res.inserted, "skipped": res.skipped},
                )
            except Exception as exc:
                logger.exception("westmetall_ingest_failed", extra={"error": str(exc)})

            # Finance pipeline daily snapshots (optional)
            if str(os.getenv("FINANCE_PIPELINE_DAILY_ENABLED", "false")).strip().lower() in {
                "1",
                "true",
                "yes",
            }:
                db = SessionLocal()
                lock_key = 912027  # stable key for finance pipeline daily
                got_lock = _try_pg_advisory_lock(db, lock_key)
                if not got_lock:
                    logger.info("finance_pipeline_daily_skipped_locked")
                    db.close()
                else:
                    try:
                        pipeline_hour = int(
                            os.getenv(
                                "FINANCE_PIPELINE_DAILY_UTC_HOUR",
                                str(DEFAULT_FINANCE_PIPELINE_UTC_HOUR),
                            )
                        )
                        as_of = datetime.now(timezone.utc)
                        # Run only after the configured UTC hour to ensure market data is ingested.
                        if as_of.hour >= pipeline_hour:
                            result = execute_finance_pipeline_daily(
                                db,
                                as_of_date=as_of.date(),
                                pipeline_version="daily.v1",
                                scope_filters=None,
                                mode="materialize",
                                emit_exports=False,
                                requested_by_user_id=None,
                                request_id=None,
                            )
                            logger.info(
                                "finance_pipeline_daily_ok",
                                extra={"as_of_date": as_of.date().isoformat(), "result": str(result)},
                            )
                        else:
                            logger.info(
                                "finance_pipeline_daily_skipped_hour",
                                extra={"as_of_date": as_of.date().isoformat(), "hour": as_of.hour},
                            )
                    except Exception as exc:
                        logger.exception(
                            "finance_pipeline_daily_failed",
                            extra={"error": str(exc)},
                        )
                    finally:
                        _unlock_pg_advisory_lock(db, lock_key)
                        db.close()


# Singleton runner for FastAPI lifecycle
runner = DailyJobRunner()

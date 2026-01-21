from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime
from collections import defaultdict, deque
from threading import Lock
from typing import Deque
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from sqlalchemy.exc import TimeoutError as SATimeoutError

_APP_START_MONOTONIC = time.monotonic()

_LATENCY_WINDOW = int(os.getenv("LATENCY_METRICS_WINDOW", "200"))
_LATENCY_LOG_EVERY = int(os.getenv("LATENCY_METRICS_LOG_EVERY", "50"))
_LATENCY_LOCK = Lock()
_LATENCY_BUCKETS: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=_LATENCY_WINDOW))

_CONCURRENCY_LIMITS_ENABLED = str(os.getenv("CONCURRENCY_LIMITS_ENABLED", "false")).lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
_DASHBOARD_CONCURRENCY_LIMIT = int(os.getenv("DASHBOARD_CONCURRENCY_LIMIT", "0"))
_DASHBOARD_QUEUE_TIMEOUT_MS = int(os.getenv("DASHBOARD_QUEUE_TIMEOUT_MS", "200"))
_EXPOSURES_CONCURRENCY_LIMIT = int(os.getenv("EXPOSURES_CONCURRENCY_LIMIT", "0"))
_EXPOSURES_QUEUE_TIMEOUT_MS = int(os.getenv("EXPOSURES_QUEUE_TIMEOUT_MS", "200"))
_QUEUE_WAIT_LOG_MS = int(os.getenv("CONCURRENCY_QUEUE_LOG_MS", "50"))

_DASHBOARD_CB_ENABLED = str(
    os.getenv("DASHBOARD_CIRCUIT_BREAKER_ENABLED", "false")
).lower() in {"1", "true", "yes", "y", "on"}
_DASHBOARD_CB_WINDOW = int(os.getenv("DASHBOARD_CB_WINDOW", "20"))
_DASHBOARD_CB_FAILURE_THRESHOLD = float(os.getenv("DASHBOARD_CB_FAILURE_THRESHOLD", "0.5"))
_DASHBOARD_CB_COOLDOWN_SECONDS = int(os.getenv("DASHBOARD_CB_COOLDOWN_SECONDS", "30"))

_SLOW_REQUEST_MS = int(os.getenv("SLOW_REQUEST_MS", "2000"))

_INFLIGHT_LOCK = asyncio.Lock()
_INFLIGHT: dict[str, int] = defaultdict(int)

_SEMAPHORES: dict[str, asyncio.Semaphore] = {}

_DASHBOARD_CB_LOCK = asyncio.Lock()
_DASHBOARD_CB_RESULTS: Deque[bool] = deque(maxlen=_DASHBOARD_CB_WINDOW)
_DASHBOARD_CB_OPEN_UNTIL = 0.0

_CRITICAL_ENDPOINTS: list[tuple[str, str, str]] = [
    ("GET", "/rfqs", "rfqs.list"),
    ("GET", "/exposures", "exposures.list"),
    ("GET", "/net-exposure", "net_exposure"),
    ("GET", "/dashboard/summary", "dashboard.summary"),
    ("GET", "/cashflow/analytic", "cashflow.analytic"),
]


def _critical_label_for(method: str, path: str) -> str | None:
    for m, suffix, label in _CRITICAL_ENDPOINTS:
        if method == m and path.endswith(suffix):
            return label
    return None


def _pool_status() -> str | None:
    try:
        from app.database import engine

        return engine.pool.status()
    except Exception:
        return None


def _concurrency_label_for(method: str, path: str) -> str | None:
    if method == "GET" and path.endswith("/dashboard/summary"):
        return "dashboard.summary"
    if method == "GET" and path.endswith("/exposures"):
        return "exposures.list"
    return None


def _get_semaphore(label: str) -> asyncio.Semaphore | None:
    if label == "dashboard.summary" and _DASHBOARD_CONCURRENCY_LIMIT > 0:
        return _SEMAPHORES.setdefault(
            "dashboard.summary",
            asyncio.Semaphore(_DASHBOARD_CONCURRENCY_LIMIT),
        )
    if label == "exposures.list" and _EXPOSURES_CONCURRENCY_LIMIT > 0:
        return _SEMAPHORES.setdefault(
            "exposures.list",
            asyncio.Semaphore(_EXPOSURES_CONCURRENCY_LIMIT),
        )
    return None


def _queue_timeout_ms_for(label: str) -> int:
    if label == "dashboard.summary":
        return _DASHBOARD_QUEUE_TIMEOUT_MS
    if label == "exposures.list":
        return _EXPOSURES_QUEUE_TIMEOUT_MS
    return 0


async def _dashboard_cb_open() -> bool:
    if not _DASHBOARD_CB_ENABLED:
        return False
    async with _DASHBOARD_CB_LOCK:
        return time.monotonic() < _DASHBOARD_CB_OPEN_UNTIL


async def _dashboard_cb_record(success: bool, logger: logging.Logger | None) -> None:
    if not _DASHBOARD_CB_ENABLED:
        return
    async with _DASHBOARD_CB_LOCK:
        _DASHBOARD_CB_RESULTS.append(bool(success))
        if len(_DASHBOARD_CB_RESULTS) < _DASHBOARD_CB_WINDOW:
            return
        failure_rate = 1.0 - (sum(_DASHBOARD_CB_RESULTS) / len(_DASHBOARD_CB_RESULTS))
        if failure_rate >= _DASHBOARD_CB_FAILURE_THRESHOLD:
            global _DASHBOARD_CB_OPEN_UNTIL
            _DASHBOARD_CB_OPEN_UNTIL = time.monotonic() + _DASHBOARD_CB_COOLDOWN_SECONDS
            if logger:
                logger.warning(
                    "dashboard_circuit_open",
                    extra={
                        "failure_rate": round(failure_rate, 3),
                        "window": len(_DASHBOARD_CB_RESULTS),
                        "cooldown_s": _DASHBOARD_CB_COOLDOWN_SECONDS,
                    },
                )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((pct / 100.0) * (len(s) - 1)))
    k = max(0, min(k, len(s) - 1))
    return float(s[k])


def _record_latency(label: str, duration_ms: float, logger: logging.Logger | None = None) -> None:
    if not label:
        return
    with _LATENCY_LOCK:
        bucket = _LATENCY_BUCKETS[label]
        bucket.append(float(duration_ms))
        if len(bucket) < _LATENCY_LOG_EVERY:
            return
        if len(bucket) % _LATENCY_LOG_EVERY != 0:
            return
        values = list(bucket)
    p50 = _percentile(values, 50)
    p95 = _percentile(values, 95)
    p99 = _percentile(values, 99)
    if logger:
        logger.info(
            "http_latency",
            extra={
                "endpoint": label,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "window": len(values),
            },
        )


def uptime_seconds() -> float:
    return max(0.0, time.monotonic() - _APP_START_MONOTONIC)


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler that returns a structured error response.

    This handler catches all unhandled exceptions and returns a clean
    JSON response without exposing internal details to the client.
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    # Log the full exception with traceback
    extra = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "exception_type": type(exc).__name__,
    }

    headers = {"X-Request-ID": request_id}

    try:
        logger = getattr(request.app.state, "logger", None)
        if logger:
            logger.exception("unhandled_exception", extra=extra)
        else:
            logging.getLogger("alcast").exception("unhandled_exception", extra=extra)
    except Exception:
        # Fallback to basic logging if app state is not available
        logging.getLogger("alcast").exception("unhandled_exception", extra=extra)

    # Attach CORS headers when the request Origin is allowed.
    # This prevents browsers from turning real 500s into opaque CORS errors.
    try:
        origin = request.headers.get("origin")
        if origin:
            allowed = set(
                getattr(getattr(request.app, "state", None), "settings_cors_origins", []) or []
            )
            if not allowed:
                from app.config import settings

                allowed = set(settings.cors_origins or [])

            if origin in allowed or "*" in allowed:
                headers.update(
                    {
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                        "Vary": "Origin",
                    }
                )
    except Exception:
        pass

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno do servidor. Tente novamente mais tarde.",
            "request_id": request_id,
            "code": "INTERNAL_SERVER_ERROR",
        },
        headers=headers,
    )


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Request-level logging middleware.

    Adds/propagates X-Request-ID and measures request duration.
    Does not log request/response bodies.
    """

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    start = time.perf_counter()
    label = _critical_label_for(request.method, request.url.path)
    concurrency_label = _concurrency_label_for(request.method, request.url.path)
    semaphore = None
    acquired = False
    wait_ms = 0.0
    inflight_after = None
    if _CONCURRENCY_LIMITS_ENABLED and concurrency_label:
        if concurrency_label == "dashboard.summary" and await _dashboard_cb_open():
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Temporarily unavailable",
                    "code": "DASHBOARD_CIRCUIT_OPEN",
                },
            )

        semaphore = _get_semaphore(concurrency_label)
        if semaphore is not None:
            queue_timeout_ms = _queue_timeout_ms_for(concurrency_label)
            wait_start = time.perf_counter()
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=queue_timeout_ms / 1000.0)
                acquired = True
            except asyncio.TimeoutError:
                if request.app.state.logger:
                    request.app.state.logger.warning(
                        "concurrency_queue_timeout",
                        extra={
                            "endpoint": concurrency_label,
                            "queue_timeout_ms": queue_timeout_ms,
                        },
                    )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Servidor ocupado. Tente novamente.",
                        "code": "CONCURRENCY_QUEUE_TIMEOUT",
                    },
                )
            finally:
                wait_ms = (time.perf_counter() - wait_start) * 1000.0
            async with _INFLIGHT_LOCK:
                _INFLIGHT[concurrency_label] += 1
                inflight_after = _INFLIGHT[concurrency_label]
            if wait_ms >= _QUEUE_WAIT_LOG_MS and request.app.state.logger:
                request.app.state.logger.info(
                    "concurrency_queue_wait",
                    extra={
                        "endpoint": concurrency_label,
                        "wait_ms": round(wait_ms, 2),
                        "inflight": inflight_after,
                    },
                )

    try:
        response: Response = await call_next(request)
    except SATimeoutError as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _record_latency(label, duration_ms, getattr(request.app.state, "logger", None))
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": round(duration_ms, 2),
            "pool_status": _pool_status(),
            "error": str(exc),
        }
        if request.app.state.logger:
            request.app.state.logger.error("db_pool_timeout", extra=extra)
        raise
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _record_latency(label, duration_ms, getattr(request.app.state, "logger", None))
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": round(duration_ms, 2),
        }

        # Prefer the app logger, but also log to uvicorn.error to ensure
        # tracebacks are visible even when uvicorn logging config disables
        # non-uvicorn loggers.
        try:
            request.app.state.logger.exception("http_request_failed", extra=extra)
        finally:
            logging.getLogger("uvicorn.error").exception("http_request_failed", extra=extra)
        if concurrency_label == "dashboard.summary":
            await _dashboard_cb_record(False, getattr(request.app.state, "logger", None))
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _record_latency(label, duration_ms, getattr(request.app.state, "logger", None))

        if duration_ms >= _SLOW_REQUEST_MS and request.app.state.logger:
            request.app.state.logger.info(
                "slow_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "pool_status": _pool_status(),
                },
            )

        # Avoid noisy logging for liveness endpoints.
        if request.url.path not in {"/health", "/healthz"}:
            request.app.state.logger.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "endpoint": label,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

        if concurrency_label == "dashboard.summary":
            await _dashboard_cb_record(response.status_code < 500, request.app.state.logger)

        response.headers.setdefault("X-Request-ID", request_id)
        return response
    finally:
        if acquired and semaphore is not None and concurrency_label:
            semaphore.release()
            async with _INFLIGHT_LOCK:
                _INFLIGHT[concurrency_label] = max(0, _INFLIGHT[concurrency_label] - 1)

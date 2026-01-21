from __future__ import annotations

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

_APP_START_MONOTONIC = time.monotonic()

_LATENCY_WINDOW = int(os.getenv("LATENCY_METRICS_WINDOW", "200"))
_LATENCY_LOG_EVERY = int(os.getenv("LATENCY_METRICS_LOG_EVERY", "50"))
_LATENCY_LOCK = Lock()
_LATENCY_BUCKETS: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=_LATENCY_WINDOW))

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

    try:
        response: Response = await call_next(request)
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
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000.0
        _record_latency(label, duration_ms, getattr(request.app.state, "logger", None))

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

        response.headers.setdefault("X-Request-ID", request_id)
        return response

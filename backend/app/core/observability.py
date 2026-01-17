from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

_APP_START_MONOTONIC = time.monotonic()


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
    try:
        response: Response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000.0
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

        # Avoid noisy logging for liveness endpoints.
        if request.url.path not in {"/health", "/healthz"}:
            request.app.state.logger.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

        response.headers.setdefault("X-Request-ID", request_id)
        return response

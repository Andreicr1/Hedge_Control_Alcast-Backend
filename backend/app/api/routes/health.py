from fastapi import APIRouter

from app.config import settings
from app.core.observability import uptime_seconds, utc_now_iso

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Healthcheck")
def healthcheck():
    """Institutional healthcheck (liveness).

    Keep payload stable for monitoring systems.
    """
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "time": utc_now_iso(),
        "uptime_seconds": round(uptime_seconds(), 2),
        "version": getattr(settings, "build_version", None),
    }

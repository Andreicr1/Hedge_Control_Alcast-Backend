from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class KycGateResult:
    allowed: bool
    reason_code: str | None = None
    blocked_counterparty_id: int | None = None
    details: dict[str, Any] | None = None


_REQUIRED_CHECK_TYPES: tuple[str, ...] = ("credit", "sanctions", "risk_flag")


def resolve_counterparty_kyc_gate(
    db: Session,
    counterparty_id: int,
    *,
    now: datetime | None = None,
) -> KycGateResult:
    """Resolve whether a counterparty is allowed for RFQ/Contract by KYC.

    Guardrails:
    - Counterparty-only gating
    - Requires counterparty.kyc_status == 'approved'
    - Requires checks pass: credit, sanctions, risk_flag
    - Checks are TTL-bound via expires_at
    """

    now = now or datetime.utcnow()

    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        return KycGateResult(
            allowed=False,
            reason_code="COUNTERPARTY_NOT_FOUND",
            blocked_counterparty_id=counterparty_id,
        )

    kyc_status = (getattr(cp, "kyc_status", None) or "").strip().lower()
    if kyc_status != "approved":
        return KycGateResult(
            allowed=False,
            reason_code="COUNTERPARTY_KYC_STATUS_NOT_APPROVED",
            blocked_counterparty_id=counterparty_id,
            details={"kyc_status": getattr(cp, "kyc_status", None)},
        )

    if bool(getattr(cp, "sanctions_flag", False)):
        return KycGateResult(
            allowed=False,
            reason_code="COUNTERPARTY_SANCTIONS_FLAGGED",
            blocked_counterparty_id=counterparty_id,
        )

    risk_rating = (getattr(cp, "risk_rating", None) or "").strip().lower()
    if risk_rating in {"high", "very_high", "critical"}:
        return KycGateResult(
            allowed=False,
            reason_code="COUNTERPARTY_RISK_RATING_BLOCKED",
            blocked_counterparty_id=counterparty_id,
            details={"risk_rating": getattr(cp, "risk_rating", None)},
        )

    ttl_by_check: dict[str, dict[str, Any]] = {}

    for check_type in _REQUIRED_CHECK_TYPES:
        check = (
            db.query(models.KycCheck)
            .filter(
                models.KycCheck.owner_type == models.DocumentOwnerType.counterparty,
                models.KycCheck.owner_id == counterparty_id,
                models.KycCheck.check_type == check_type,
            )
            .order_by(models.KycCheck.created_at.desc())
            .first()
        )
        if not check:
            return KycGateResult(
                allowed=False,
                reason_code="KYC_CHECK_MISSING",
                blocked_counterparty_id=counterparty_id,
                details={
                    "check_type": check_type,
                    "missing_items": [check_type],
                    "ttl_info": {"by_check": ttl_by_check} if ttl_by_check else None,
                },
            )

        ttl_by_check[check_type] = {
            "created_at": check.created_at.isoformat() if check.created_at else None,
            "expires_at": check.expires_at.isoformat() if check.expires_at else None,
            "status": check.status,
        }

        if check.expires_at and check.expires_at <= now:
            return KycGateResult(
                allowed=False,
                reason_code="KYC_CHECK_EXPIRED",
                blocked_counterparty_id=counterparty_id,
                details={
                    "check_type": check_type,
                    "expires_at": check.expires_at.isoformat(),
                    "expired_items": [check_type],
                    "ttl_info": {"by_check": ttl_by_check} if ttl_by_check else None,
                },
            )

        if (check.status or "").strip().lower() != "pass":
            return KycGateResult(
                allowed=False,
                reason_code="KYC_CHECK_FAILED",
                blocked_counterparty_id=counterparty_id,
                details={
                    "check_type": check_type,
                    "status": check.status,
                    "ttl_info": {"by_check": ttl_by_check} if ttl_by_check else None,
                },
            )

    # Observability only: include TTL info for the passing checks.
    return KycGateResult(allowed=True, details={"ttl_info": {"by_check": ttl_by_check}})

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class SoKycGateResult:
    allowed: bool
    reason_code: str | None = None
    so_id: int | None = None
    customer_id: int | None = None
    customer_kyc_status: str | None = None
    details: dict[str, Any] | None = None


def resolve_so_kyc_gate(
    *,
    db: Session,
    so_id: int,
    now: datetime | None = None,
) -> SoKycGateResult:
    """Resolve whether a Sales Order (SO) is allowed for RFQ/Contract actions.

    Institutional rule (locked): KYC is Sales-side (Customer/SO).

    Current implementation uses Customer attributes already present in the domain model:
    - customer.kyc_status must be 'approved'
    - customer.sanctions_flag must not be true
    - customer.risk_rating must not be high/very_high/critical

    Note: This is a deterministic read-only resolver.
    """

    _ = now  # reserved for future TTL-based rules

    so = db.get(models.SalesOrder, so_id)
    if not so:
        return SoKycGateResult(allowed=False, reason_code="SO_NOT_FOUND", so_id=so_id)

    customer = db.get(models.Customer, so.customer_id)
    if not customer:
        return SoKycGateResult(
            allowed=False,
            reason_code="CUSTOMER_NOT_FOUND",
            so_id=so.id,
            customer_id=so.customer_id,
        )

    kyc_status = (getattr(customer, "kyc_status", None) or "").strip().lower() or None
    if kyc_status != "approved":
        return SoKycGateResult(
            allowed=False,
            reason_code="CUSTOMER_KYC_STATUS_NOT_APPROVED",
            so_id=so.id,
            customer_id=customer.id,
            customer_kyc_status=getattr(customer, "kyc_status", None),
            details={"kyc_status": getattr(customer, "kyc_status", None)},
        )

    if bool(getattr(customer, "sanctions_flag", False)):
        return SoKycGateResult(
            allowed=False,
            reason_code="CUSTOMER_SANCTIONS_FLAGGED",
            so_id=so.id,
            customer_id=customer.id,
            customer_kyc_status=getattr(customer, "kyc_status", None),
        )

    risk_rating = (getattr(customer, "risk_rating", None) or "").strip().lower()
    if risk_rating in {"high", "very_high", "critical"}:
        return SoKycGateResult(
            allowed=False,
            reason_code="CUSTOMER_RISK_RATING_BLOCKED",
            so_id=so.id,
            customer_id=customer.id,
            customer_kyc_status=getattr(customer, "kyc_status", None),
            details={"risk_rating": getattr(customer, "risk_rating", None)},
        )

    return SoKycGateResult(
        allowed=True,
        so_id=so.id,
        customer_id=customer.id,
        customer_kyc_status=getattr(customer, "kyc_status", None),
    )

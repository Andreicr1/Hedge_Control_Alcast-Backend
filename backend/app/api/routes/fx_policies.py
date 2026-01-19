from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.fx_policy import FxPolicyCreate, FxPolicyRead

router = APIRouter(prefix="/fx/policies", tags=["fx"])

_db_dep = Depends(get_db)
_finance_or_admin_dep = Depends(require_roles(models.RoleName.financeiro, models.RoleName.admin))
_finance_admin_or_audit_dep = Depends(
    require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
)


def _parse_policy_key(policy_key: str) -> tuple[str, str, str]:
    """Parse canonical policy_key: "BRL:^USDBRL@barchart_excel_usdbrl" -> (BRL, ^USDBRL, barchart_excel_usdbrl)."""
    s = (policy_key or "").strip()
    if not s or ":" not in s:
        raise ValueError("invalid policy_key")

    reporting_currency, rhs = s.split(":", 1)
    reporting_currency = (reporting_currency or "").strip().upper()

    if not reporting_currency:
        raise ValueError("invalid reporting_currency")

    if "@" not in rhs:
        raise ValueError("invalid policy_key")

    fx_symbol, fx_source = rhs.split("@", 1)
    fx_symbol = (fx_symbol or "").strip()
    fx_source = (fx_source or "").strip()

    if not fx_symbol or not fx_source:
        raise ValueError("invalid policy_key")

    # Canonicalize: keep user-provided symbol/source casing, but currency uppercase.
    canonical = f"{reporting_currency}:{fx_symbol}@{fx_source}"
    return canonical, reporting_currency, fx_symbol, fx_source


@router.post("", response_model=FxPolicyRead, status_code=status.HTTP_200_OK)
def upsert_fx_policy(
    payload: FxPolicyCreate,
    db: Session = _db_dep,
    current_user: models.User = _finance_or_admin_dep,
):
    try:
        canonical, reporting_currency, fx_symbol, fx_source = _parse_policy_key(payload.policy_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = (
        db.query(models.FxPolicyMap).filter(models.FxPolicyMap.policy_key == canonical).first()
    )
    if existing is not None:
        return existing

    row = models.FxPolicyMap(
        policy_key=canonical,
        reporting_currency=reporting_currency,
        fx_symbol=fx_symbol,
        fx_source=fx_source,
        active=bool(payload.active),
        notes=payload.notes,
        created_by_user_id=getattr(current_user, "id", None),
    )
    db.add(row)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Idempotent retry under concurrency
        row = (
            db.query(models.FxPolicyMap).filter(models.FxPolicyMap.policy_key == canonical).first()
        )
        if row is None:
            raise

    return row


@router.get("", response_model=list[FxPolicyRead])
def list_fx_policies(
    db: Session = _db_dep,
    current_user: models.User = _finance_admin_or_audit_dep,
    reporting_currency: str | None = Query(None),
    active: bool | None = Query(None),
):
    q = db.query(models.FxPolicyMap)

    if reporting_currency:
        q = q.filter(models.FxPolicyMap.reporting_currency == reporting_currency.strip().upper())
    if active is not None:
        q = q.filter(models.FxPolicyMap.active.is_(bool(active)))

    return q.order_by(
        models.FxPolicyMap.reporting_currency.asc(),
        models.FxPolicyMap.policy_key.asc(),
        models.FxPolicyMap.id.asc(),
    ).all()

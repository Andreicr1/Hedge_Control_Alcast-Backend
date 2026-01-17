import os
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.config import settings
from app.database import get_db
from app.schemas import (
    CounterpartyCreate,
    CounterpartyRead,
    CounterpartyUpdate,
    KycCheckRead,
    KycDocumentRead,
    KycPreflightResponse,
)
from app.services import kyc as kyc_service
from app.services.kyc_gate import resolve_counterparty_kyc_gate
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(prefix="/counterparties", tags=["counterparties"])


@router.get("", response_model=List[CounterpartyRead])
def list_counterparties(
    q: str | None = Query(None, description="Busca rápida (nome, documento, e-mail, telefone)."),
    limit: int = Query(200, ge=1, le=500, description="Limite de registros retornados."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    query = db.query(models.Counterparty)

    if q:
        term = q.strip()
        if term:
            like_any = f"%{term}%"
            like_prefix = f"{term}%"
            query = query.filter(
                or_(
                    models.Counterparty.name.ilike(like_any),
                    models.Counterparty.trade_name.ilike(like_any),
                    models.Counterparty.legal_name.ilike(like_any),
                    models.Counterparty.contact_name.ilike(like_any),
                    models.Counterparty.contact_email.ilike(like_any),
                    models.Counterparty.contact_phone.ilike(like_any),
                    models.Counterparty.tax_id.ilike(like_prefix),
                )
            )

    return query.order_by(models.Counterparty.name.asc()).limit(limit).all()


@router.post("", response_model=CounterpartyRead, status_code=status.HTTP_201_CREATED)
def create_counterparty(
    payload: CounterpartyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    if db.query(models.Counterparty).filter(models.Counterparty.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Counterparty already exists"
        )
    cp = models.Counterparty(**payload.dict(exclude_unset=True))
    db.add(cp)
    db.commit()
    db.refresh(cp)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    cp_type = getattr(cp, "type", None)
    emit_timeline_event(
        db=db,
        event_type="COUNTERPARTY_CREATED",
        subject_type="counterparty",
        subject_id=int(cp.id),
        correlation_id=correlation_id,
        idempotency_key=f"counterparty:{cp.id}:created",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "counterparty_id": cp.id,
            "name": cp.name,
            "type": cp_type.value if hasattr(cp_type, "value") else str(cp_type) if cp_type else None,
        },
    )
    return cp


@router.put("/{counterparty_id}", response_model=CounterpartyRead)
def update_counterparty(
    counterparty_id: int,
    payload: CounterpartyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")

    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(cp, field, value)

    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


@router.delete("/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_counterparty(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    db.delete(cp)
    db.commit()


@router.get("/{counterparty_id}/documents", response_model=List[KycDocumentRead])
def list_counterparty_documents(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    return (
        db.query(models.KycDocument)
        .filter(
            models.KycDocument.owner_type == models.DocumentOwnerType.counterparty,
            models.KycDocument.owner_id == counterparty_id,
        )
        .order_by(models.KycDocument.uploaded_at.desc())
        .all()
    )


@router.post(
    "/{counterparty_id}/documents",
    response_model=KycDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_counterparty_document(
    counterparty_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")

    storage_root = os.path.abspath(settings.storage_dir)
    os.makedirs(storage_root, exist_ok=True)
    cp_dir = os.path.join(storage_root, "counterparties", str(counterparty_id))
    os.makedirs(cp_dir, exist_ok=True)

    allowed_types = {"application/pdf", "image/png", "image/jpeg"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File too large (max 5MB)"
        )

    safe_name = os.path.basename(file.filename or "upload")
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    file_path = os.path.join(cp_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    doc = models.KycDocument(
        owner_type=models.DocumentOwnerType.counterparty,
        owner_id=counterparty_id,
        filename=file.filename,
        content_type=file.content_type,
        path=file_path,
        metadata_json={"uploaded_by": getattr(current_user, "email", None)},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_timeline_event(
        db=db,
        event_type="COUNTERPARTY_DOCUMENT_UPLOADED",
        subject_type="counterparty",
        subject_id=int(counterparty_id),
        correlation_id=correlation_id,
        idempotency_key=f"counterparty_document:{doc.id}:uploaded",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "counterparty_id": counterparty_id,
            "document_id": doc.id,
            "filename": doc.filename,
            "content_type": doc.content_type,
            "uploaded_by_email": getattr(current_user, "email", None),
        },
    )
    return doc


@router.get("/{counterparty_id}/kyc/checks", response_model=List[KycCheckRead])
def list_counterparty_kyc_checks(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")

    return (
        db.query(models.KycCheck)
        .filter(
            models.KycCheck.owner_type == models.DocumentOwnerType.counterparty,
            models.KycCheck.owner_id == counterparty_id,
        )
        .order_by(models.KycCheck.created_at.desc())
        .all()
    )


@router.post(
    "/{counterparty_id}/kyc/checks/{check_type}",
    response_model=KycCheckRead,
    status_code=status.HTTP_201_CREATED,
)
def run_counterparty_kyc_check(
    counterparty_id: int,
    check_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    cp = db.get(models.Counterparty, counterparty_id)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")

    check_type = (check_type or "").strip().lower()
    allowed = {"credit", "sanctions", "risk_flag"}
    if check_type not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid check_type")

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)

    status_value = "pass"
    score = None
    details_json: dict | None = None

    if check_type == "credit":
        result = kyc_service.run_credit_check("counterparty", counterparty_id, cp.name)
        score = result.score
        status_value = "pass" if result.status == "approved" else "fail"
        details_json = {
            "bureau": result.bureau,
            "summary": result.summary,
            "raw_status": result.status,
        }
    elif check_type == "sanctions":
        flagged = bool(getattr(cp, "sanctions_flag", False))
        status_value = "fail" if flagged else "pass"
        details_json = {"sanctions_flag": flagged}
    elif check_type == "risk_flag":
        rating = (getattr(cp, "risk_rating", None) or "").strip().lower()
        blocked = rating in {"high", "very_high", "critical"}
        status_value = "fail" if blocked else "pass"
        details_json = {"risk_rating": getattr(cp, "risk_rating", None)}

    check = models.KycCheck(
        owner_type=models.DocumentOwnerType.counterparty,
        owner_id=counterparty_id,
        check_type=check_type,
        status=status_value,
        score=score,
        details_json=details_json,
        expires_at=expires_at,
    )
    db.add(check)
    db.commit()
    db.refresh(check)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_timeline_event(
        db=db,
        event_type="COUNTERPARTY_CHECK_CREATED",
        subject_type="counterparty",
        subject_id=int(counterparty_id),
        correlation_id=correlation_id,
        idempotency_key=f"counterparty_check:{check.id}:created",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "counterparty_id": counterparty_id,
            "check_id": check.id,
            "check_type": check.check_type,
            "status": check.status,
            "score": check.score,
            "expires_at": check.expires_at.isoformat() if check.expires_at else None,
        },
    )
    return check


@router.get("/{counterparty_id}/kyc/preflight", response_model=KycPreflightResponse)
def kyc_preflight_counterparty(
    counterparty_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    """Read-only KYC introspection for Counterparties.

    Thin wrapper over the deterministic resolver:
    - No persistence
    - No audit side effects
    - No impact on enforcement (RFQ/Contract remain authoritative)
    """

    gate = resolve_counterparty_kyc_gate(db=db, counterparty_id=counterparty_id)

    details = gate.details if isinstance(gate.details, dict) else {}
    missing_items = list(details.get("missing_items") or [])
    expired_items = list(details.get("expired_items") or [])
    ttl_info = details.get("ttl_info")

    return KycPreflightResponse(
        allowed=bool(gate.allowed),
        reason_code=gate.reason_code,
        blocked_counterparty_id=gate.blocked_counterparty_id,
        missing_items=missing_items,
        expired_items=expired_items,
        ttl_info=ttl_info,
    )

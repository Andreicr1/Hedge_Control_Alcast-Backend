import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.config import settings
from app.database import get_db
from app.schemas import (
    CreditCheckRead,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    KycDocumentRead,
)
from app.services import kyc as kyc_service
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=List[CustomerRead])
def list_customers(
    q: str | None = Query(None, description="Busca rápida (nome, documento, e-mail, código)."),
    limit: int = Query(200, ge=1, le=500, description="Limite de registros retornados."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    query = db.query(models.Customer)

    if q:
        term = q.strip()
        if term:
            like_any = f"%{term}%"
            like_prefix = f"{term}%"
            query = query.filter(
                or_(
                    models.Customer.name.ilike(like_any),
                    models.Customer.trade_name.ilike(like_any),
                    models.Customer.legal_name.ilike(like_any),
                    models.Customer.contact_email.ilike(like_any),
                    models.Customer.tax_id.ilike(like_prefix),
                    models.Customer.code.ilike(like_prefix),
                )
            )

    return query.order_by(models.Customer.name.asc()).limit(limit).all()


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    if db.query(models.Customer).filter(models.Customer.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Customer already exists"
        )
    cust = models.Customer(**payload.dict(exclude_unset=True))
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(customer, field, value)

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()


@router.get("/{customer_id}/documents", response_model=List[KycDocumentRead])
def list_customer_documents(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return (
        db.query(models.KycDocument)
        .filter(
            models.KycDocument.owner_type == models.DocumentOwnerType.customer,
            models.KycDocument.owner_id == customer_id,
        )
        .order_by(models.KycDocument.uploaded_at.desc())
        .all()
    )


@router.post(
    "/{customer_id}/documents", response_model=KycDocumentRead, status_code=status.HTTP_201_CREATED
)
def upload_customer_document(
    customer_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    storage_root = os.path.abspath(settings.storage_dir)
    os.makedirs(storage_root, exist_ok=True)
    cust_dir = os.path.join(storage_root, "customers", str(customer_id))
    os.makedirs(cust_dir, exist_ok=True)

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
    file_path = os.path.join(cust_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    doc = models.KycDocument(
        owner_type=models.DocumentOwnerType.customer,
        owner_id=customer_id,
        filename=file.filename,
        content_type=file.content_type,
        path=file_path,
        metadata_json={"uploaded_by": current_user.email},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_timeline_event(
        db=db,
        event_type="KYC_DOCUMENT_UPLOADED",
        subject_type="customer",
        subject_id=int(customer_id),
        correlation_id=correlation_id,
        idempotency_key=f"kyc_document:{doc.id}:uploaded",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "customer_id": customer_id,
            "document_id": doc.id,
            "filename": doc.filename,
            "content_type": doc.content_type,
            "uploaded_by_email": getattr(current_user, "email", None),
        },
    )
    return doc


@router.post(
    "/{customer_id}/credit-check",
    response_model=CreditCheckRead,
    status_code=status.HTTP_201_CREATED,
)
def run_customer_credit_check(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.vendas)
    ),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    result = kyc_service.run_credit_check("customer", customer_id, customer.name)
    check = models.CreditCheck(
        owner_type=models.DocumentOwnerType.customer,
        owner_id=customer_id,
        bureau=result.bureau,
        score=result.score,
        status=result.status,
        raw_response=result.summary,
    )
    customer.kyc_status = result.status
    customer.credit_score = result.score
    db.add(check)
    db.add(customer)
    db.commit()
    db.refresh(check)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_timeline_event(
        db=db,
        event_type="KYC_STATUS_CHANGED",
        subject_type="customer",
        subject_id=int(customer_id),
        correlation_id=correlation_id,
        idempotency_key=f"customer:{customer_id}:kyc_status:{customer.kyc_status}",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "customer_id": customer_id,
            "kyc_status": customer.kyc_status,
            "reason_code": "credit_check",
            "details": {
                "bureau": result.bureau,
                "score": result.score,
            },
        },
    )
    return check

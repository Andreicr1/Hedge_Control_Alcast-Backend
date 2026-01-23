import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.config import settings
from app.database import get_db
from app.schemas import (
    CreditCheckRead,
    KycDocumentRead,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from app.services import kyc as kyc_service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=List[SupplierRead])
def list_suppliers(
    q: str | None = Query(None, description="Busca rápida (nome, documento, e-mail, código)."),
    limit: int = Query(200, ge=1, le=500, description="Limite de registros retornados."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    query = db.query(models.Supplier)

    if q:
        term = q.strip()
        if term:
            like_any = f"%{term}%"
            like_prefix = f"{term}%"
            query = query.filter(
                or_(
                    models.Supplier.name.ilike(like_any),
                    models.Supplier.trade_name.ilike(like_any),
                    models.Supplier.legal_name.ilike(like_any),
                    models.Supplier.contact_email.ilike(like_any),
                    models.Supplier.tax_id.ilike(like_prefix),
                    models.Supplier.code.ilike(like_prefix),
                )
            )

    return query.order_by(models.Supplier.name.asc()).limit(limit).all()


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    if db.query(models.Supplier).filter(models.Supplier.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier already exists"
        )
    sup = models.Supplier(**payload.dict(exclude_unset=True))
    db.add(sup)
    db.commit()
    db.refresh(sup)
    return sup


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(supplier, field, value)

    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    db.delete(supplier)
    db.commit()


@router.get("/{supplier_id}/documents", response_model=List[KycDocumentRead])
def list_supplier_documents(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return (
        db.query(models.KycDocument)
        .filter(
            models.KycDocument.owner_type == models.DocumentOwnerType.supplier,
            models.KycDocument.owner_id == supplier_id,
        )
        .order_by(models.KycDocument.uploaded_at.desc())
        .all()
    )


@router.post(
    "/{supplier_id}/documents", response_model=KycDocumentRead, status_code=status.HTTP_201_CREATED
)
def upload_supplier_document(
    supplier_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    storage_root = os.path.abspath(settings.storage_dir)
    os.makedirs(storage_root, exist_ok=True)
    supplier_dir = os.path.join(storage_root, "suppliers", str(supplier_id))
    os.makedirs(supplier_dir, exist_ok=True)

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
    file_path = os.path.join(supplier_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    doc = models.KycDocument(
        owner_type=models.DocumentOwnerType.supplier,
        owner_id=supplier_id,
        filename=file.filename,
        content_type=file.content_type,
        path=file_path,
        metadata_json={"uploaded_by": current_user.email},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.post(
    "/{supplier_id}/kyp-check", response_model=CreditCheckRead, status_code=status.HTTP_201_CREATED
)
def run_supplier_kyp(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    result = kyc_service.run_credit_check("supplier", supplier_id, supplier.name)
    check = models.CreditCheck(
        owner_type=models.DocumentOwnerType.supplier,
        owner_id=supplier_id,
        bureau=result.bureau,
        score=result.score,
        status=result.status,
        raw_response=result.summary,
    )
    supplier.kyc_status = result.status
    supplier.credit_score = result.score
    db.add(check)
    db.add(supplier)
    db.commit()
    db.refresh(check)
    return check

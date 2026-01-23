from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import WarehouseLocationCreate, WarehouseLocationRead, WarehouseLocationUpdate

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=List[WarehouseLocationRead])
def list_locations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial, models.RoleName.estoque)
    ),
):
    return db.query(models.WarehouseLocation).order_by(models.WarehouseLocation.name.asc()).all()


@router.post("", response_model=WarehouseLocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: WarehouseLocationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial, models.RoleName.estoque)
    ),
):
    existing = (
        db.query(models.WarehouseLocation)
        .filter(models.WarehouseLocation.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Location already exists"
        )
    loc = models.WarehouseLocation(
        name=payload.name,
        type=payload.type,
        current_stock_mt=payload.current_stock_mt,
        capacity_mt=payload.capacity_mt,
        active=payload.active,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/{location_id}", response_model=WarehouseLocationRead)
def update_location(
    location_id: int,
    payload: WarehouseLocationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial, models.RoleName.estoque)
    ),
):
    loc = db.get(models.WarehouseLocation, location_id)
    if not loc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(loc, field, value)

    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc

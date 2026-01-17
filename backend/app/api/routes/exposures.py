from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import ExposureRead

router = APIRouter(prefix="/exposures", tags=["exposures"])


@router.get("", response_model=List[ExposureRead])
def list_exposures(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    return (
        db.query(models.Exposure)
        .options(selectinload(models.Exposure.tasks))
        .order_by(models.Exposure.created_at.desc())
        .all()
    )

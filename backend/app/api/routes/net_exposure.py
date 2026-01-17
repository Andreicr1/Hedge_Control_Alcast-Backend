from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.services.exposure_aggregation import NetExposureRow, compute_net_exposure

router = APIRouter(prefix="/net-exposure", tags=["net_exposure"])


@router.get("", response_model=List[NetExposureRow])
def get_net_exposure(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
    product: Optional[str] = Query(None),
    period: Optional[str] = Query(None, description="Formato YYYY-MM"),
):
    return compute_net_exposure(db, product=product, period=period)

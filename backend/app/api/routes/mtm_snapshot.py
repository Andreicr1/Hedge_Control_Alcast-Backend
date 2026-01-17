from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import MTMSnapshotCreate, MTMSnapshotRead
from app.services.mtm_snapshot_service import create_snapshot, list_snapshots
from app.services.mtm_timeline import emit_mtm_snapshot_created
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/mtm/snapshots", tags=["mtm_snapshots"])


@router.post("", response_model=MTMSnapshotRead, status_code=status.HTTP_201_CREATED)
def create_mtm_snapshot(
    request: Request,
    payload: MTMSnapshotCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    try:
        snap = create_snapshot(db, payload)

        correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
        emit_mtm_snapshot_created(
            db=db,
            snapshot=snap,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
        )
        return snap
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[MTMSnapshotRead])
def get_mtm_snapshots(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
    object_type: Optional[models.MarketObjectType] = Query(None),
    object_id: Optional[int] = Query(None),
    product: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    latest: bool = Query(False),
):
    snaps = list_snapshots(
        db,
        object_type=object_type,
        object_id=object_id,
        product=product,
        period=period,
        latest=latest,
    )
    return snaps

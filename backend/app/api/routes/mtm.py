from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import MtmComputeRequest, MtmComputeResponse, MtmRecordCreate, MtmRecordRead
from app.services.audit import audit_event
from app.services.mtm_service import (
    compute_mtm_for_hedge,
    compute_mtm_for_order,
    compute_mtm_portfolio,
)
from app.services.mtm_timeline import emit_mtm_record_created
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/mtm", tags=["mtm"])


@router.post("", response_model=MtmRecordRead, status_code=status.HTTP_201_CREATED)
def create_mtm_record(
    request: Request,
    payload: MtmRecordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    record = models.MtmRecord(
        as_of_date=payload.as_of_date,
        object_type=payload.object_type,
        object_id=payload.object_id,
        forward_price=payload.forward_price,
        fx_rate=payload.fx_rate,
        mtm_value=payload.mtm_value,
        methodology=payload.methodology,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    audit_event(
        "mtm.created",
        current_user.id,
        {
            "mtm_id": record.id,
            "object_type": record.object_type.value,
            "object_id": record.object_id,
        },
    )

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_mtm_record_created(
        db=db,
        record=record,
        correlation_id=correlation_id,
        actor_user_id=getattr(current_user, "id", None),
    )
    return record


@router.get(
    "",
    response_model=List[MtmRecordRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def list_mtm_records(
    db: Session = Depends(get_db),
    object_type: Optional[models.MarketObjectType] = None,
    object_id: Optional[int] = None,
):
    query = db.query(models.MtmRecord)
    if object_type:
        query = query.filter(models.MtmRecord.object_type == object_type)
    if object_id:
        query = query.filter(models.MtmRecord.object_id == object_id)
    return query.order_by(models.MtmRecord.as_of_date.desc()).limit(200).all()


@router.post(
    "/compute",
    response_model=MtmComputeResponse,
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def compute_mtm(payload: MtmComputeRequest, db: Session = Depends(get_db)):
    fx_symbol = payload.fx_symbol
    source = payload.pricing_source
    haircut_pct = payload.haircut_pct
    price_shift = payload.price_shift

    if payload.object_type == models.MarketObjectType.hedge:
        res = compute_mtm_for_hedge(
            db,
            payload.object_id,
            fx_symbol=fx_symbol,
            pricing_source=source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
    elif payload.object_type == models.MarketObjectType.po:
        res = compute_mtm_for_order(
            db,
            payload.object_id,
            is_purchase=True,
            fx_symbol=fx_symbol,
            pricing_source=source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
    elif payload.object_type == models.MarketObjectType.so:
        res = compute_mtm_for_order(
            db,
            payload.object_id,
            is_purchase=False,
            fx_symbol=fx_symbol,
            pricing_source=source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
    elif payload.object_type == models.MarketObjectType.portfolio:
        res = compute_mtm_portfolio(
            db,
            fx_symbol=fx_symbol,
            pricing_source=source,
            haircut_pct=haircut_pct,
            price_shift=price_shift,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported object_type")

    if res is None:
        raise HTTPException(status_code=404, detail="Object or market price not found")
    return MtmComputeResponse(
        object_type=payload.object_type,
        object_id=payload.object_id or 0,
        mtm_value=res.mtm_value,
        fx_rate=res.fx_rate,
        scenario_mtm_value=res.scenario_mtm_value,
        haircut_pct=haircut_pct,
        price_shift=price_shift,
    )

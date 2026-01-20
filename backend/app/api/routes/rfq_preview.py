from fastapi import APIRouter, Depends, HTTPException, status

from app import models
from app.api.deps import require_roles
from app.schemas.rfq_preview import LegInput, RfqPreviewRequest, RfqPreviewResponse
from app.services import rfq_engine

router = APIRouter(prefix="/rfqs", tags=["rfq_preview"])


def _build_leg(payload_leg: LegInput, qty: float) -> rfq_engine.Leg:
    order = None
    if payload_leg.order:
        order = rfq_engine.OrderInstruction(
            order_type=payload_leg.order.order_type,
            validity=payload_leg.order.validity,
            limit_price=payload_leg.order.limit_price,
        )

    return rfq_engine.Leg(
        side=payload_leg.side,
        price_type=payload_leg.price_type,
        quantity_mt=qty,
        month_name=payload_leg.month_name,
        year=payload_leg.year,
        start_date=payload_leg.start_date,
        end_date=payload_leg.end_date,
        fixing_date=payload_leg.fixing_date,
        ppt=payload_leg.ppt,
        order=order,
    )


@router.post(
    "/preview",
    response_model=RfqPreviewResponse,
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
    status_code=status.HTTP_200_OK,
)
def preview_rfq(payload: RfqPreviewRequest) -> RfqPreviewResponse:
    """
    Build RFQ text using the Python rfq_engine (parity with Andreicr1/RFQ-Generator).
    """
    cal = rfq_engine.HolidayCalendar(payload.holidays)
    try:
        leg1 = _build_leg(payload.leg1, payload.leg1.quantity_mt)
        leg2 = _build_leg(payload.leg2, payload.leg2.quantity_mt) if payload.leg2 else None

        trade = rfq_engine.RfqTrade(
            trade_type=payload.trade_type,
            leg1=leg1,
            leg2=leg2,
            sync_ppt=payload.sync_ppt,
        )

        text = rfq_engine.generate_rfq_text(
            trade,
            cal=cal,
            company_header=payload.company_header,
            company_label_for_payoff=payload.company_label_for_payoff,
            language=payload.language,
        )
        return RfqPreviewResponse(text=text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="RFQ preview failed"
        ) from exc

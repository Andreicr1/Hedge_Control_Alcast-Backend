from app import models
from app.services.rfq_engine import Leg, PriceType, RfqTrade, Side, TradeType, generate_rfq_text


def build_rfq_message(
    rfq: models.Rfq, counterparty: models.Counterparty, lme_text: str | None = None
) -> str:
    channel_type = (counterparty.rfq_channel_type or "BROKER_LME").upper()

    if channel_type == "BANK":
        qty = rfq.quantity_mt
        sentido = "Compra" if (getattr(rfq, "side", "buy") == "buy") else "Venda"
        periodo = rfq.period
        return (
            "Bom dia,\n\n"
            "RFQ – Alcast\n\n"
            f"{sentido}: {qty} toneladas de alumínio LME\n"
            "Preço: conforme condições técnicas LME, com média mensal (Monthly Average) e datas conforme especificação do RFQ\n\n"
            f"Período: {periodo}\n\n"
            "Fico no aguardo da cotação."
        )

    # Default to broker/LME technical text
    if lme_text:
        return lme_text

    # Fallback: minimal LME text from RFQ scalar data
    trade = RfqTrade(
        trade_type=TradeType.FORWARD,
        leg1=Leg(
            side=Side.BUY if getattr(rfq, "side", "buy") == "buy" else Side.SELL,
            price_type=PriceType.AVG,
            quantity_mt=rfq.quantity_mt,
            month_name="",
            year=0,
        ),
        leg2=None,
    )
    return generate_rfq_text(trade)

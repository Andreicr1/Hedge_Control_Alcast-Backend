"""
Pure-Python RFQ text engine compatible with the wording/ordering rules used in the
legacy RFQ-Generator repo (Andreicr1/RFQ-Generator).

Design goals
- Deterministic, side-effect-free RFQ message generation (except optional holiday loading).
- Backend-friendly: no UI/DOM assumptions.
- Output strings match the legacy “dialect” (punctuation, ordering, line breaks).

Key behaviors mirrored from legacy JS:
- Swap vs Forward wording
- Fixed leg ordering preference in Swap (“Fix/C2R first” when paired with AVG/AVGInter)
- Special formatting for Fix vs C2R (“Official Settlement Price of ...”)
- PPT rules: AVG -> 2nd business day of next month; AVGInter -> +2 biz days after end date;
  Fix/C2R -> +2 biz days after fixing date (unless overridden by pairing logic)
- Execution Instruction for Limit/Resting (and default Day validity if missing)
- Expected Payoff wording and pay/receive direction based on fixed leg side
- Resting + Fix (no fixing date) paired with AVG adds “, ppt <date>” to AVG leg

You can wrap this module with FastAPI endpoints (preview/create/send) and persist in Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Tuple

# -----------------------------
# Enums / Data Models
# -----------------------------


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    def verb(self) -> str:
        return "Buy" if self == Side.BUY else "Sell"


class PriceType(str, Enum):
    AVG = "AVG"
    AVG_INTER = "AVGInter"
    FIX = "Fix"
    C2R = "C2R"


class TradeType(str, Enum):
    SWAP = "Swap"
    FORWARD = "Forward"


class OrderType(str, Enum):
    AT_MARKET = "At Market"
    LIMIT = "Limit"
    RANGE = "Range"  # reserved
    RESTING = "Resting"


@dataclass(frozen=True)
class OrderInstruction:
    order_type: OrderType
    validity: Optional[str] = None  # e.g. "Day", "GTC", "3 Hours", etc.
    limit_price: Optional[str] = None  # keep as string to preserve formatting (e.g., "2300")


@dataclass(frozen=True)
class Leg:
    side: Side
    price_type: PriceType
    quantity_mt: float

    # AVG fields
    month_name: Optional[str] = None  # e.g., "January"
    year: Optional[int] = None  # e.g., 2025

    # AVGInter fields
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # Fix/C2R fields
    fixing_date: Optional[date] = None

    # Computed/overridden PPT (if caller sets, it takes precedence)
    ppt: Optional[date] = None

    # Optional order instruction (relevant for Fix/C2R legs)
    order: Optional[OrderInstruction] = None


@dataclass(frozen=True)
class RfqTrade:
    trade_type: TradeType
    leg1: Leg
    leg2: Optional[Leg] = None  # None for Forward single-leg
    sync_ppt: bool = False  # Forward + sync_ppt generates two lines if both legs exist


@dataclass(frozen=True)
class ValidationError:
    code: str
    message: str


# -----------------------------
# Calendar / Business Day Support
# -----------------------------


class HolidayCalendar:
    """
    Pluggable business-day calendar.

    Default: weekends + optional holiday set (ISO YYYY-MM-DD).
    """

    def __init__(self, holidays_iso: Optional[Iterable[str]] = None) -> None:
        self._holidays: Set[str] = set(holidays_iso or [])

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:  # 5=Sat, 6=Sun
            return False
        return d.isoformat() not in self._holidays

    def add_holidays(self, holidays_iso: Iterable[str]) -> None:
        self._holidays.update(holidays_iso)


def add_business_days(start: date, n: int, cal: HolidayCalendar) -> date:
    """
    Return the date that is n business days after start (excluding start day),
    matching legacy logic that increments day-by-day and counts business days.
    """
    d = start
    counted = 0
    while counted < n:
        d = d + timedelta(days=1)
        if cal.is_business_day(d):
            counted += 1
    return d


def second_business_day_of_next_month(year: int, month_index_0: int, cal: HolidayCalendar) -> date:
    """
    month_index_0: 0=Jan ... 11=Dec
    Legacy: getSecondBusinessDay(year, month) builds Date(year, month+1, 1)
    and counts the 2nd business day from there.
    """
    if month_index_0 == 11:
        y2, m2 = year + 1, 1
    else:
        y2, m2 = year, month_index_0 + 2  # datetime month is 1-based
    d = date(y2, m2, 1)
    count = 0
    while True:
        if cal.is_business_day(d):
            count += 1
            if count == 2:
                return d
        d = d + timedelta(days=1)


def last_business_day_of_month(year: int, month_index_0: int, cal: HolidayCalendar) -> date:
    """
    Used by legacy UI to auto-fill fixing dates for Fix when paired with AVG,
    but message generation for Fix vs AVG actually omits fixing date and aligns PPT.
    Provided here for completeness.
    """
    if month_index_0 == 11:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month_index_0 + 2, 1) - timedelta(days=1)
    while not cal.is_business_day(d):
        d = d - timedelta(days=1)
    return d


# -----------------------------
# Formatting helpers
# -----------------------------

MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTH_INDEX: Dict[str, int] = {m: i for i, m in enumerate(MONTHS_EN)}
MONTHS_PT = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def fmt_date_short(d: date) -> str:
    """Legacy format: DD/MM/YY"""
    return d.strftime("%d/%m/%y")


def fmt_date_pt(d: date) -> str:
    """Bank-friendly format: DD/MM/YYYY."""
    return d.strftime("%d/%m/%Y")


def month_name_pt(month_name_en: Optional[str]) -> Optional[str]:
    if not month_name_en:
        return None
    idx = MONTH_INDEX.get(month_name_en)
    if idx is None:
        return None
    return MONTHS_PT[idx]


def fmt_qty(qty: float) -> str:
    """
    Legacy uses raw numeric string from parseFloat in JS; tests show integers.
    Keep integers without trailing .0; otherwise trim trailing zeros.
    """
    if float(int(qty)) == float(qty):
        return str(int(qty))
    s = f"{qty:.10f}".rstrip("0").rstrip(".")
    return s


# -----------------------------
# PPT computation (mirrors legacy)
# -----------------------------


def compute_ppt_for_leg(leg: Leg, cal: HolidayCalendar) -> Optional[date]:
    """
    Mirrors legacy:
    - AVG: 2nd business day of next month
    - AVGInter: 2 business days after end_date
    - Fix/C2R: 2 business days after fixing_date
    """
    if leg.ppt is not None:
        return leg.ppt

    if leg.price_type == PriceType.AVG:
        if leg.month_name is None or leg.year is None:
            return None
        idx = MONTH_INDEX.get(leg.month_name)
        if idx is None:
            return None
        return second_business_day_of_next_month(leg.year, idx, cal)

    if leg.price_type == PriceType.AVG_INTER:
        if leg.end_date is None:
            return None
        return add_business_days(leg.end_date, 2, cal)

    if leg.price_type in (PriceType.FIX, PriceType.C2R):
        if leg.fixing_date is None:
            return None
        return add_business_days(leg.fixing_date, 2, cal)

    return None


# -----------------------------
# Leg text (mirrors legacy legText)
# -----------------------------


def build_leg_text(leg: Leg, cal: HolidayCalendar) -> str:
    s = leg.side.verb()
    qty = fmt_qty(leg.quantity_mt)
    txt = f"{s} {qty} mt Al "

    ppt = compute_ppt_for_leg(leg, cal)
    ppt_str = fmt_date_short(ppt) if ppt else ""

    if leg.price_type == PriceType.AVG:
        if not leg.month_name or leg.year is None:
            return (txt + "AVG").strip()
        txt += f"AVG {leg.month_name} {leg.year} Flat"
        return txt

    if leg.price_type == PriceType.AVG_INTER:
        if not leg.start_date or not leg.end_date:
            return (txt + "Fixing AVG").strip()
        ss = fmt_date_short(leg.start_date)
        ee = fmt_date_short(leg.end_date)
        txt += f"Fixing AVG {ss} to {ee}"
        if ppt_str:
            txt += f", ppt {ppt_str}"
        return txt

    if leg.price_type == PriceType.FIX:
        txt += "USD"
        if ppt_str:
            txt += f" ppt {ppt_str}"
        return txt

    if leg.price_type == PriceType.C2R:
        if leg.fixing_date is None:
            return (txt + "C2R").strip()
        f = fmt_date_short(leg.fixing_date)
        p = ppt_str or fmt_date_short(add_business_days(leg.fixing_date, 2, cal))
        txt += f"C2R {f} ppt {p}"
        return txt

    return txt.strip()


def build_leg_text_pt(leg: Leg, cal: HolidayCalendar) -> str:
    """Simplified Portuguese wording for banks."""
    side = "Compra" if leg.side == Side.BUY else "Venda"
    qty = fmt_qty(leg.quantity_mt)

    product = "Alumínio Primário"

    if leg.price_type == PriceType.AVG:
        month = month_name_pt(leg.month_name) or (leg.month_name or "")
        if month and leg.year is not None:
            return f"{side} de {qty} MT de {product}, Média {month} {leg.year}".strip()
        return f"{side} de {qty} MT de {product}, Média".strip()

    if leg.price_type == PriceType.AVG_INTER:
        if leg.start_date and leg.end_date:
            ss = fmt_date_pt(leg.start_date)
            ee = fmt_date_pt(leg.end_date)
            return f"{side} de {qty} MT de {product}, Média de {ss} a {ee}"
        return f"{side} de {qty} MT de {product}, Média (período a definir)".strip()

    if leg.price_type == PriceType.FIX:
        if leg.fixing_date:
            return f"{side} de {qty} MT de {product}, Data de Fixação: {fmt_date_pt(leg.fixing_date)}"
        return f"{side} de {qty} MT de {product}, Preço fixo".strip()

    if leg.price_type == PriceType.C2R:
        if leg.fixing_date:
            return f"{side} de {qty} MT de {product}, C2R em {fmt_date_pt(leg.fixing_date)}"
        return f"{side} de {qty} MT de {product}, C2R".strip()

    return f"{side} de {qty} MT de {product}".strip()


# -----------------------------
# Execution Instruction (Limit / Resting)
# -----------------------------


def build_execution_instruction(order: OrderInstruction, side: Side) -> str:
    """
    Matches legacy test strings exactly:
    - Limit: "Please work this order as a Limit @ USD <price> for the Fixed price, valid for Day."
    - Resting: "Please work this order posting as the best bid/offer in the book for the fixed price, valid for Day."
      NOTE: legacy behavior flips bid/offer relative to side.
    """
    validity = order.validity or "Day"

    if order.order_type == OrderType.LIMIT:
        price = (order.limit_price or "").strip()
        return f"Please work this order as a Limit @ USD {price} for the Fixed price, valid for {validity}."

    if order.order_type == OrderType.RESTING:
        best = "best offer" if side == Side.BUY else "best bid"
        return f"Please work this order posting as the {best} in the book for the fixed price, valid for {validity}."

    return f"Please work this order, valid for {validity}."


# -----------------------------
# Expected Payoff
# -----------------------------


def build_expected_payoff_text(
    fixed_leg: Leg,
    other_leg: Optional[Leg],
    cal: HolidayCalendar,
    company_label: str = "Alcast",
) -> str:
    pays_when_higher = fixed_leg.side == Side.SELL

    receives_if_higher = not pays_when_higher
    pays_if_higher = pays_when_higher

    def _pays_or_receives(is_higher: bool) -> str:
        if is_higher:
            return "receives" if receives_if_higher else "pays"
        return "pays" if receives_if_higher else "receives"

    if other_leg is not None and other_leg.price_type in (PriceType.AVG, PriceType.AVG_INTER):
        if (
            other_leg.price_type == PriceType.AVG
            and other_leg.month_name
            and other_leg.year is not None
        ):
            month_year = f"{other_leg.month_name} {other_leg.year}"
        elif other_leg.price_type == PriceType.AVG_INTER and other_leg.end_date:
            month_year = f"{MONTHS_EN[other_leg.end_date.month - 1]} {other_leg.end_date.year}"
        else:
            month_year = "the relevant month"

        return (
            "Expected Payoff:\n"
            f"If official Monthly Average of {month_year} is higher than the Fixed Price, {company_label} "
            f"{_pays_or_receives(True)} the difference. If the average is lower, {company_label} "
            f"{_pays_or_receives(False)} the difference."
        )

    official_date: Optional[date] = None
    if other_leg is not None and other_leg.price_type == PriceType.C2R and other_leg.fixing_date:
        official_date = other_leg.fixing_date
    elif fixed_leg.fixing_date:
        official_date = fixed_leg.fixing_date

    official_str = fmt_date_short(official_date) if official_date else "the relevant date"

    return (
        "Expected Payoff:\n"
        f"If the official price of {official_str} is higher than the Fixed Price, {company_label} "
        f"{_pays_or_receives(True)} the difference. If the official price is lower, {company_label} "
        f"{_pays_or_receives(False)} the difference."
    )


def build_expected_payoff_text_pt(
    fixed_leg: Leg,
    other_leg: Optional[Leg],
    cal: HolidayCalendar,
    company_label: str = "Alcast",
) -> str:
    """Simplified Portuguese payoff hint for banks."""
    pays_when_higher = fixed_leg.side == Side.SELL
    action_high = "paga" if pays_when_higher else "recebe"
    action_low = "recebe" if pays_when_higher else "paga"

    # Keep text generic; banks usually want directionality, not full algebra.
    return (
        f"Se o preço realizado for maior que o preço fixado, {company_label} {action_high} a diferença.\n"
        f"Se o preço realizado for menor que o preço fixado, {company_label} {action_low} a diferença."
    )


# -----------------------------
# Validation (mirrors legacy rules)
# -----------------------------


def validate_trade(trade: RfqTrade) -> List[ValidationError]:
    errs: List[ValidationError] = []

    def _validate_leg(leg: Leg, idx: int) -> None:
        if leg.quantity_mt is None or not isinstance(leg.quantity_mt, (int, float)):
            errs.append(
                ValidationError("qty_invalid", f"Leg {idx}: Please enter a valid quantity.")
            )
            return
        if leg.quantity_mt <= 0:
            errs.append(
                ValidationError(
                    "qty_non_positive", f"Leg {idx}: Quantity must be greater than zero."
                )
            )

        if leg.price_type == PriceType.C2R and leg.fixing_date is None:
            errs.append(ValidationError("missing_fixing_date", "Please provide a fixing date."))

        if leg.price_type == PriceType.AVG:
            if not leg.month_name or leg.year is None:
                errs.append(
                    ValidationError(
                        "avg_missing_month_year", f"Leg {idx}: AVG requires month/year."
                    )
                )

        if leg.price_type == PriceType.AVG_INTER:
            if not leg.start_date or not leg.end_date:
                errs.append(
                    ValidationError(
                        "avginter_missing_dates", f"Leg {idx}: AVGInter requires start/end."
                    )
                )
            elif leg.start_date > leg.end_date:
                errs.append(
                    ValidationError(
                        "avginter_bad_range", f"Leg {idx}: Start date must be <= end date."
                    )
                )

    _validate_leg(trade.leg1, 1)
    if trade.leg2 is not None:
        _validate_leg(trade.leg2, 2)

    return errs


# -----------------------------
# Core RFQ message builder
# -----------------------------


def generate_rfq_text(
    trade: RfqTrade,
    cal: Optional[HolidayCalendar] = None,
    company_header: Optional[str] = None,
    company_label_for_payoff: str = "Alcast",
    language: str = "en",
) -> str:
    cal = cal or HolidayCalendar()

    errs = validate_trade(trade)
    if errs:
        raise ValueError(errs[0].message)

    l1 = trade.leg1
    l2 = trade.leg2

    def _compute_pair_overrides(leg_a: Leg, leg_b: Optional[Leg]) -> Tuple[Leg, Optional[Leg]]:
        if leg_b is None:
            return leg_a, None

        a = leg_a
        b = leg_b

        ppt_a = compute_ppt_for_leg(a, cal)
        ppt_b = compute_ppt_for_leg(b, cal)

        if (
            a.price_type == PriceType.AVG_INTER
            and b.price_type in (PriceType.FIX, PriceType.C2R)
            and a.end_date
        ):
            b_fix = a.end_date
            b_ppt = ppt_a if trade.sync_ppt else ppt_b
            b = Leg(**{**b.__dict__, "fixing_date": b_fix, "ppt": b_ppt})
            ppt_b = b_ppt
        if (
            b.price_type == PriceType.AVG_INTER
            and a.price_type in (PriceType.FIX, PriceType.C2R)
            and b.end_date
        ):
            a_fix = b.end_date
            a_ppt = ppt_b if trade.sync_ppt else ppt_a
            a = Leg(**{**a.__dict__, "fixing_date": a_fix, "ppt": a_ppt})
            ppt_a = a_ppt

        if a.price_type == PriceType.FIX and b.price_type == PriceType.AVG:
            a = Leg(**{**a.__dict__, "ppt": ppt_b, "fixing_date": None})
            ppt_a = ppt_b
        if b.price_type == PriceType.FIX and a.price_type == PriceType.AVG:
            b = Leg(**{**b.__dict__, "ppt": ppt_a, "fixing_date": None})
            ppt_b = ppt_a

        if a.price_type == PriceType.FIX and b.price_type == PriceType.C2R:
            a = Leg(**{**a.__dict__, "ppt": ppt_b, "fixing_date": None})
            ppt_a = ppt_b
        if b.price_type == PriceType.FIX and a.price_type == PriceType.C2R:
            b = Leg(**{**b.__dict__, "ppt": ppt_a, "fixing_date": None})
            ppt_b = ppt_a

        if trade.sync_ppt and a.price_type == PriceType.AVG_INTER:
            b = Leg(**{**b.__dict__, "ppt": ppt_a})
        if trade.sync_ppt and b.price_type == PriceType.AVG_INTER:
            a = Leg(**{**a.__dict__, "ppt": compute_ppt_for_leg(b, cal)})

        return a, b

    l1_adj, l2_adj = _compute_pair_overrides(l1, l2)

    if str(language).strip().lower() == "pt":
        # Bank-oriented output: multi-line, simplified Portuguese.
        ppt: Optional[date] = None
        for candidate in (
            l1_adj if l1_adj.price_type in (PriceType.AVG, PriceType.AVG_INTER) else None,
            l2_adj if l2_adj and l2_adj.price_type in (PriceType.AVG, PriceType.AVG_INTER) else None,
            l1_adj,
            l2_adj,
        ):
            if candidate is None:
                continue
            ppt = compute_ppt_for_leg(candidate, cal)
            if ppt:
                break

        ppt_str = fmt_date_pt(ppt) if ppt else None

        order_leg = l1_adj if l1_adj.order else (l2_adj if (l2_adj and l2_adj.order) else None)
        if order_leg and order_leg.order:
            validity = order_leg.order.validity or "Day"
            if order_leg.order.order_type == OrderType.LIMIT:
                price = (order_leg.order.limit_price or "").strip()
                exec_pt = f"Limite @ USD {price} (validade: {validity})".strip()
            elif order_leg.order.order_type == OrderType.RESTING:
                exec_pt = f"Ordem em aberto (validade: {validity})"
            else:
                exec_pt = str(order_leg.order.order_type.value)
        else:
            exec_pt = "A Mercado"

        lines: List[str] = []
        if company_header:
            lines.append(str(company_header).strip())
            lines.append("")

        lines.append("Operação 1")
        lines.append("----------")
        lines.append(build_leg_text_pt(l1_adj, cal))
        if ppt_str:
            lines.append(f"Data de Pagamento: {ppt_str}")

        if l2_adj is not None:
            lines.append("")
            lines.append(build_leg_text_pt(l2_adj, cal))
            if ppt_str:
                lines.append(f"Data de Pagamento: {ppt_str}")

        lines.append("")
        lines.append(f"Execução: {exec_pt}")

        payoff_pt = None
        if l2_adj is None:
            if l1_adj.price_type == PriceType.FIX and l1_adj.fixing_date:
                payoff_pt = build_expected_payoff_text_pt(
                    fixed_leg=l1_adj,
                    other_leg=None,
                    cal=cal,
                    company_label=company_label_for_payoff,
                )
        else:
            fix_types = {PriceType.FIX, PriceType.C2R}
            if l1_adj.price_type in fix_types and l2_adj.price_type in (PriceType.AVG, PriceType.AVG_INTER):
                payoff_pt = build_expected_payoff_text_pt(
                    fixed_leg=l1_adj,
                    other_leg=l2_adj,
                    cal=cal,
                    company_label=company_label_for_payoff,
                )
            elif l2_adj.price_type in fix_types and l1_adj.price_type in (PriceType.AVG, PriceType.AVG_INTER):
                payoff_pt = build_expected_payoff_text_pt(
                    fixed_leg=l2_adj,
                    other_leg=l1_adj,
                    cal=cal,
                    company_label=company_label_for_payoff,
                )

        if payoff_pt:
            lines.append("")
            lines.append(payoff_pt)

        return "\n".join(lines).strip()

    leg1_text = build_leg_text(l1_adj, cal)
    leg2_text = build_leg_text(l2_adj, cal) if l2_adj else None

    if trade.trade_type == TradeType.SWAP and l2_adj is not None:
        if l1_adj.price_type == PriceType.FIX and l2_adj.price_type == PriceType.C2R:
            f = fmt_date_short(l2_adj.fixing_date) if l2_adj.fixing_date else ""
            ppt2 = compute_ppt_for_leg(l2_adj, cal)
            ppt2s = fmt_date_short(ppt2) if ppt2 else ""
            leg2_text = f"{l2_adj.side.verb()} {fmt_qty(l2_adj.quantity_mt)} mt Al Official Settlement Price of {f}, PPT {ppt2s}"
        elif l1_adj.price_type == PriceType.C2R and l2_adj.price_type == PriceType.FIX:
            f = fmt_date_short(l1_adj.fixing_date) if l1_adj.fixing_date else ""
            ppt1 = compute_ppt_for_leg(l1_adj, cal)
            ppt1s = fmt_date_short(ppt1) if ppt1 else ""
            leg1_text = f"{l1_adj.side.verb()} {fmt_qty(l1_adj.quantity_mt)} mt Al Official Settlement Price of {f}, PPT {ppt1s}"

    if l2_adj is not None:
        if (
            l1_adj.price_type == PriceType.FIX
            and (l1_adj.order and l1_adj.order.order_type == OrderType.RESTING)
            and (l1_adj.fixing_date is None)
            and l2_adj.price_type == PriceType.AVG
        ):
            ppt1 = compute_ppt_for_leg(l1_adj, cal)
            if ppt1:
                leg2_text = (leg2_text or "") + f", ppt {fmt_date_short(ppt1)}"
        if (
            l2_adj.price_type == PriceType.FIX
            and (l2_adj.order and l2_adj.order.order_type == OrderType.RESTING)
            and (l2_adj.fixing_date is None)
            and l1_adj.price_type == PriceType.AVG
        ):
            ppt2 = compute_ppt_for_leg(l2_adj, cal)
            if ppt2:
                leg1_text = (leg1_text or "") + f", ppt {fmt_date_short(ppt2)}"

    text = ""

    if trade.trade_type == TradeType.FORWARD and trade.sync_ppt and l2_adj is not None:
        text = f"How can I {leg1_text}?\nHow can I {leg2_text}?"
    elif trade.trade_type == TradeType.FORWARD and l2_adj is None:
        text = f"How can I {leg1_text}?"
    elif (
        trade.trade_type == TradeType.FORWARD and l2_adj is not None and (l2_adj.price_type is None)
    ):
        text = f"How can I {leg1_text}?"
    else:
        assert l2_adj is not None and leg2_text is not None

        fix_types = {PriceType.FIX, PriceType.C2R}

        if l1_adj.price_type == PriceType.FIX and l2_adj.price_type == PriceType.C2R:
            text = f"How can I {leg1_text} and {leg2_text} against?"
        elif l1_adj.price_type == PriceType.C2R and l2_adj.price_type == PriceType.FIX:
            text = f"How can I {leg2_text} and {leg1_text} against?"
        else:
            if l1_adj.price_type in fix_types and l2_adj.price_type not in fix_types:
                text = f"How can I {leg1_text} and {leg2_text} against?"
            elif l2_adj.price_type in fix_types and l1_adj.price_type not in fix_types:
                text = f"How can I {leg2_text} and {leg1_text} against?"
            else:
                text = f"How can I {leg1_text} and {leg2_text} against?"

    exec_line = None
    if l1_adj.order and l1_adj.order.order_type in (OrderType.LIMIT, OrderType.RESTING):
        exec_line = build_execution_instruction(
            OrderInstruction(
                order_type=l1_adj.order.order_type,
                validity=l1_adj.order.validity or "Day",
                limit_price=l1_adj.order.limit_price,
            ),
            l1_adj.side,
        )
    elif (
        l2_adj and l2_adj.order and l2_adj.order.order_type in (OrderType.LIMIT, OrderType.RESTING)
    ):
        exec_line = build_execution_instruction(
            OrderInstruction(
                order_type=l2_adj.order.order_type,
                validity=l2_adj.order.validity or "Day",
                limit_price=l2_adj.order.limit_price,
            ),
            l2_adj.side,
        )

    if exec_line:
        text += f"\nExecution Instruction: {exec_line}"

    payoff = None
    if l2_adj is None:
        if l1_adj.price_type == PriceType.FIX and l1_adj.fixing_date:
            payoff = build_expected_payoff_text(
                fixed_leg=l1_adj,
                other_leg=None,
                cal=cal,
                company_label=company_label_for_payoff,
            )
    else:
        if l1_adj.price_type in (PriceType.FIX, PriceType.C2R) and l2_adj.price_type in (
            PriceType.AVG,
            PriceType.AVG_INTER,
        ):
            payoff = build_expected_payoff_text(
                fixed_leg=l1_adj,
                other_leg=l2_adj,
                cal=cal,
                company_label=company_label_for_payoff,
            )
        elif l2_adj.price_type in (PriceType.FIX, PriceType.C2R) and l1_adj.price_type in (
            PriceType.AVG,
            PriceType.AVG_INTER,
        ):
            payoff = build_expected_payoff_text(
                fixed_leg=l2_adj,
                other_leg=l1_adj,
                cal=cal,
                company_label=company_label_for_payoff,
            )
        elif l1_adj.price_type == PriceType.FIX and l2_adj.price_type == PriceType.C2R:
            payoff = build_expected_payoff_text(
                fixed_leg=l1_adj,
                other_leg=l2_adj,
                cal=cal,
                company_label=company_label_for_payoff,
            )
        elif l1_adj.price_type == PriceType.C2R and l2_adj.price_type == PriceType.FIX:
            payoff = build_expected_payoff_text(
                fixed_leg=l2_adj,
                other_leg=l1_adj,
                cal=cal,
                company_label=company_label_for_payoff,
            )

    if payoff:
        text += f"\n{payoff}"

    if company_header:
        text = f"For {company_header} Account:\n{text}"

    return text


def compute_trade_ppt_dates(
    trade: RfqTrade,
    cal: Optional[HolidayCalendar] = None,
) -> dict:
    """
    Compute PPT (settlement) dates for a trade using the exact same pairing/override
    rules used by generate_rfq_text().

    Returns:
      {
        "leg1_ppt": date | None,
        "leg2_ppt": date | None,
        "trade_ppt": date | None,   # max of available leg PPTs
      }
    """
    cal = cal or HolidayCalendar()
    errs = validate_trade(trade)
    if errs:
        raise ValueError(errs[0].message)

    l1 = trade.leg1
    l2 = trade.leg2

    def _compute_pair_overrides(leg_a: Leg, leg_b: Optional[Leg]) -> Tuple[Leg, Optional[Leg]]:
        if leg_b is None:
            return leg_a, None

        a = leg_a
        b = leg_b

        ppt_a = compute_ppt_for_leg(a, cal)
        ppt_b = compute_ppt_for_leg(b, cal)

        if (
            a.price_type == PriceType.AVG_INTER
            and b.price_type in (PriceType.FIX, PriceType.C2R)
            and a.end_date
        ):
            b_fix = a.end_date
            b_ppt = ppt_a if trade.sync_ppt else ppt_b
            b = Leg(**{**b.__dict__, "fixing_date": b_fix, "ppt": b_ppt})
            ppt_b = b_ppt
        if (
            b.price_type == PriceType.AVG_INTER
            and a.price_type in (PriceType.FIX, PriceType.C2R)
            and b.end_date
        ):
            a_fix = b.end_date
            a_ppt = ppt_b if trade.sync_ppt else ppt_a
            a = Leg(**{**a.__dict__, "fixing_date": a_fix, "ppt": a_ppt})
            ppt_a = a_ppt

        if a.price_type == PriceType.FIX and b.price_type == PriceType.AVG:
            a = Leg(**{**a.__dict__, "ppt": ppt_b, "fixing_date": None})
            ppt_a = ppt_b
        if b.price_type == PriceType.FIX and a.price_type == PriceType.AVG:
            b = Leg(**{**b.__dict__, "ppt": ppt_a, "fixing_date": None})
            ppt_b = ppt_a

        if a.price_type == PriceType.FIX and b.price_type == PriceType.C2R:
            a = Leg(**{**a.__dict__, "ppt": ppt_b, "fixing_date": None})
            ppt_a = ppt_b
        if b.price_type == PriceType.FIX and a.price_type == PriceType.C2R:
            b = Leg(**{**b.__dict__, "ppt": ppt_a, "fixing_date": None})
            ppt_b = ppt_a

        if trade.sync_ppt and a.price_type == PriceType.AVG_INTER:
            b = Leg(**{**b.__dict__, "ppt": ppt_a})
        if trade.sync_ppt and b.price_type == PriceType.AVG_INTER:
            a = Leg(**{**a.__dict__, "ppt": compute_ppt_for_leg(b, cal)})

        return a, b

    l1_adj, l2_adj = _compute_pair_overrides(l1, l2)
    ppt1 = compute_ppt_for_leg(l1_adj, cal)
    ppt2 = compute_ppt_for_leg(l2_adj, cal) if l2_adj else None

    pts = [d for d in (ppt1, ppt2) if d is not None]
    trade_ppt = max(pts) if pts else None
    return {"leg1_ppt": ppt1, "leg2_ppt": ppt2, "trade_ppt": trade_ppt}


if __name__ == "__main__":
    cal = HolidayCalendar()
    t = RfqTrade(
        trade_type=TradeType.SWAP,
        leg1=Leg(
            side=Side.BUY,
            price_type=PriceType.AVG,
            quantity_mt=10,
            month_name="January",
            year=2025,
        ),
        leg2=Leg(
            side=Side.SELL,
            price_type=PriceType.AVG,
            quantity_mt=10,
            month_name="February",
            year=2025,
        ),
    )
    print(generate_rfq_text(t, cal=cal, company_header="Alcast Brasil"))

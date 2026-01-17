from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Optional

LME_ALU_URL = "https://www.lme.com/en/metals/non-ferrous/lme-aluminium#Intraday+data"
LME_ALU_TRADING_SUMMARY_URL = (
    "https://www.lme.com/en/metals/non-ferrous/lme-aluminium#Trading+summary"
)


@dataclass(frozen=True)
class LmeIntradayQuoteRow:
    contract: str
    bid_qty_lots: Optional[int]
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    ask_qty_lots: Optional[int]


@dataclass(frozen=True)
class LmeLastTradedRow:
    contract: str
    last_price: Optional[Decimal]
    pct_change: Optional[Decimal]
    abs_change: Optional[Decimal]
    last_trade_time_utc: Optional[str]
    prev_close: Optional[Decimal]


@dataclass(frozen=True)
class LmeAluminumIntradaySnapshot:
    as_of_date: date
    currency: str  # "USD"
    quotes: list[LmeIntradayQuoteRow]
    last_traded: list[LmeLastTradedRow]
    raw: dict[str, Any]


@dataclass(frozen=True)
class LmeAluminumDashboardPrices:
    as_of_date: date
    currency: str  # "USD"
    cash_bid: Decimal
    cash_ask: Decimal
    three_month_last: Decimal
    three_month_last_time_utc: Optional[str]


def _parse_decimal(s: str) -> Optional[Decimal]:
    s = (s or "").strip()
    if not s or s == "-":
        return None
    # remove thousand separators if any
    s = s.replace(",", "")
    try:
        return Decimal(s)
    except Exception:
        return None


def _parse_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        return int(s)
    except Exception:
        return None


def _parse_lme_date(label: str) -> date:
    # Example: "02 Jan 2026"
    return datetime.strptime(label.strip(), "%d %b %Y").date()


async def fetch_lme_aluminum_intraday_snapshot(
    headless: bool = True,
) -> LmeAluminumIntradaySnapshot:
    """
    Fetch day-delayed intraday tables published on LME public website.

    Note:
    - This uses a real browser (Playwright) because Cloudflare blocks simple HTTP clients.
    - Requires Playwright browsers installed on the host (e.g. `python -m playwright install chromium`).
    """
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Dependência opcional ausente: instale Playwright para usar o wrapper público da LME "
            "(ex.: `pip install playwright` e depois `python -m playwright install chromium`)."
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()
        await page.goto(LME_ALU_URL, wait_until="domcontentloaded")

        # Wait for intraday content to render (tables visible)
        await page.get_by_text("Intraday prices").wait_for(timeout=30000)

        # Date label (e.g. 02 Jan 2026)
        date_text = (
            await page.locator("text=Intraday prices")
            .locator("..")
            .locator("text=/\\d{2} \\w{3} \\d{4}/")
            .first.inner_text()
        )
        as_of_date = _parse_lme_date(date_text)

        # "Prices in US$"
        currency_text = await page.locator("text=Prices in").first.inner_text()
        currency = (
            "USD" if "US$" in currency_text else currency_text.replace("Prices in", "").strip()
        )

        # Quotes table: first table under "Electronic quotes..."
        quotes_rows = page.locator("table").nth(0).locator("tbody tr")
        quotes: list[LmeIntradayQuoteRow] = []
        for i in range(await quotes_rows.count()):
            row = quotes_rows.nth(i)
            cells = [
                await row.locator("th,td").nth(j).inner_text()
                for j in range(await row.locator("th,td").count())
            ]
            if len(cells) < 5:
                continue
            quotes.append(
                LmeIntradayQuoteRow(
                    contract=cells[0].strip(),
                    bid_qty_lots=_parse_int(cells[1]),
                    bid=_parse_decimal(cells[2]),
                    ask=_parse_decimal(cells[3]),
                    ask_qty_lots=_parse_int(cells[4]),
                )
            )

        # Last traded table: second table
        last_rows = page.locator("table").nth(1).locator("tbody tr")
        last_traded: list[LmeLastTradedRow] = []
        for i in range(await last_rows.count()):
            row = last_rows.nth(i)
            cells = [
                await row.locator("th,td").nth(j).inner_text()
                for j in range(await row.locator("th,td").count())
            ]
            if len(cells) < 6:
                continue
            last_traded.append(
                LmeLastTradedRow(
                    contract=cells[0].strip(),
                    last_price=_parse_decimal(cells[1]),
                    pct_change=_parse_decimal(cells[2].replace("+", "").replace("%", "")),
                    abs_change=_parse_decimal(cells[3].replace("+", "")),
                    last_trade_time_utc=cells[4].strip() if cells[4].strip() != "-" else None,
                    prev_close=_parse_decimal(cells[5]),
                )
            )

        raw = {
            "as_of_date": as_of_date.isoformat(),
            "currency_text": currency_text,
            "quotes_count": len(quotes),
            "last_traded_count": len(last_traded),
        }
        await context.close()
        await browser.close()

        return LmeAluminumIntradaySnapshot(
            as_of_date=as_of_date,
            currency=currency,
            quotes=quotes,
            last_traded=last_traded,
            raw=raw,
        )


async def fetch_lme_aluminum_dashboard_prices(headless: bool = True) -> LmeAluminumDashboardPrices:
    """
    Fetch the two prices requested for the dashboard:
    - Cash (official bid/offer) from Trading summary table
    - 3-month last traded from Intraday data table

    Both are public / day-delayed values shown on LME.com.
    """
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Dependência opcional ausente: instale Playwright para usar o wrapper público da LME "
            "(ex.: `pip install playwright` e depois `python -m playwright install chromium`)."
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()

        # 1) Trading summary: cash bid/offer + date label
        await page.goto(LME_ALU_TRADING_SUMMARY_URL, wait_until="domcontentloaded")
        await page.get_by_text("Trading SUMMARY").wait_for(timeout=30000)

        # Date label (e.g. 02 Jan 2026)
        date_label = await page.locator("text=/\\d{2} \\w{3} \\d{4}/").first.inner_text()
        as_of_date = _parse_lme_date(date_label)

        currency_text = await page.locator("text=Prices in").first.inner_text()
        currency = (
            "USD" if "US$" in currency_text else currency_text.replace("Prices in", "").strip()
        )

        # Official Prices table: find row headers "Cash" and "3-month"
        official_table = page.get_by_role("table").filter(has=page.get_by_text("Contract"))
        # Take the first table under "Official Prices" (page layout stable)
        official_rows = page.locator("table").nth(0).locator("tbody tr")
        cash_bid = cash_ask = None
        for i in range(await official_rows.count()):
            row = official_rows.nth(i)
            cells = [
                await row.locator("th,td").nth(j).inner_text()
                for j in range(await row.locator("th,td").count())
            ]
            if len(cells) < 3:
                continue
            contract = cells[0].strip().lower()
            if contract == "cash":
                cash_bid = _parse_decimal(cells[1])
                cash_ask = _parse_decimal(cells[2])
                break
        if cash_bid is None or cash_ask is None:
            raise RuntimeError("Não consegui extrair Cash bid/offer da tabela Official Prices")

        # 2) Intraday data: 3-month last traded price + last trade time UTC
        await page.goto(LME_ALU_URL, wait_until="domcontentloaded")
        await page.get_by_text("Intraday prices").wait_for(timeout=30000)

        last_rows = page.locator("table").nth(1).locator("tbody tr")
        three_month_last = None
        three_month_time = None
        for i in range(await last_rows.count()):
            row = last_rows.nth(i)
            cells = [
                await row.locator("th,td").nth(j).inner_text()
                for j in range(await row.locator("th,td").count())
            ]
            if len(cells) < 6:
                continue
            contract = cells[0].strip().lower()
            if contract == "3-month":
                three_month_last = _parse_decimal(cells[1])
                three_month_time = cells[4].strip() if cells[4].strip() != "-" else None
                break
        if three_month_last is None:
            raise RuntimeError(
                "Não consegui extrair 3-month last traded da tabela Intraday (Last traded prices)"
            )

        await context.close()
        await browser.close()

        return LmeAluminumDashboardPrices(
            as_of_date=as_of_date,
            currency=currency,
            cash_bid=cash_bid,
            cash_ask=cash_ask,
            three_month_last=three_month_last,
            three_month_last_time_utc=three_month_time,
        )


def snapshot_as_of_datetime_utc(s: LmeAluminumIntradaySnapshot) -> datetime:
    """
    Build a conservative as_of timestamp:
    - Uses as_of_date at 00:00 UTC when last trade time is unavailable.
    - If "3-month" row has last_trade_time_utc, combine date + that time in UTC.
    """
    t = None
    for r in s.last_traded:
        if r.contract.lower() == "3-month" and r.last_trade_time_utc:
            try:
                t = datetime.strptime(r.last_trade_time_utc, "%H:%M:%S").time()
            except Exception:
                t = None
            break
    if t is None:
        t = time(0, 0, 0)
    return datetime.combine(s.as_of_date, t, tzinfo=timezone.utc)

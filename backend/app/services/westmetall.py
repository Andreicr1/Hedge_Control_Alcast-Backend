from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Optional
from urllib.request import Request, urlopen

WESTMETALL_DAILY_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash"


@dataclass(frozen=True)
class WestmetallDailyRow:
    as_of_date: date
    cash_settlement: Optional[float]
    three_month_settlement: Optional[float]
    stock: Optional[float]


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _parse_westmetall_date(s: str) -> Optional[date]:
    # Example: "31. December 2025"
    raw = (s or "").strip()
    if not raw:
        return None
    try:
        day_part, rest = raw.split(".", 1)
        day = int(day_part.strip())
        rest = rest.strip()
        month_name, year_str = rest.split(" ", 1)
        month = _MONTHS.get(month_name.strip().lower())
        year = int(year_str.strip())
        if not month:
            return None
        return date(year, month, day)
    except Exception:
        return None


def _parse_number(s: str) -> Optional[float]:
    raw = (s or "").strip()
    if not raw or raw == "-":
        return None
    # Westmetall uses "2,968.00" formatting
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except Exception:
        return None


class _TableParser(HTMLParser):
    """
    Extract the first table body under a given year anchor (e.g. #y2025).
    We keep it intentionally simple/robust: parse <tr>/<td> text content only.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_td = False
        self._in_tr = False
        self._buf: list[str] = []
        self._cells: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() == "tr":
            self._in_tr = True
            self._cells = []
        if tag.lower() == "td" and self._in_tr:
            self._in_td = True
            self._buf = []

    def handle_endtag(self, tag: str):
        if tag.lower() == "td" and self._in_td:
            self._in_td = False
            text = "".join(self._buf).strip()
            self._cells.append(" ".join(text.split()))
        if tag.lower() == "tr" and self._in_tr:
            self._in_tr = False
            if self._cells:
                self.rows.append(self._cells)
            self._cells = []

    def handle_data(self, data: str):
        if self._in_td:
            self._buf.append(data)


def fetch_westmetall_daily_rows(year: int) -> list[WestmetallDailyRow]:
    """
    Fetch Westmetall daily table and parse only the section for the given year.
    The year navigation uses anchors (e.g. <a id="y2025"></a>).
    """
    req = Request(
        WESTMETALL_DAILY_URL,
        headers={
            "User-Agent": "Hedge-Control-Alcast/1.0 (Westmetall ingest; contact: finance ops)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    html = urlopen(req, timeout=30).read().decode("utf-8", "ignore")

    start_anchor = f'<a id="y{int(year)}"></a>'
    start_idx = html.find(start_anchor)
    if start_idx < 0:
        return []

    # Next year anchor (y{year-1}) marks the end of this year's section.
    # If not found, parse until end of document.
    end_anchor = f'<a id="y{int(year) - 1}"></a>'
    end_idx = html.find(end_anchor, start_idx + len(start_anchor))
    section = html[start_idx : (end_idx if end_idx > 0 else None)]

    parser = _TableParser()
    parser.feed(section)

    out: list[WestmetallDailyRow] = []
    for cells in parser.rows:
        # Expect: [date, cash, 3m, stock] but some rows may be headers or malformed.
        if len(cells) < 3:
            continue
        d = _parse_westmetall_date(cells[0])
        if not d or d.year != int(year):
            continue
        cash = _parse_number(cells[1])
        three_m = _parse_number(cells[2]) if len(cells) >= 3 else None
        stock = _parse_number(cells[3]) if len(cells) >= 4 else None
        out.append(
            WestmetallDailyRow(
                as_of_date=d,
                cash_settlement=cash,
                three_month_settlement=three_m,
                stock=stock,
            )
        )
    return out


def as_of_datetime_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)

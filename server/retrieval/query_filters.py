"""Pull a company (ticker) and a year window out of a natural-language question.

Used to narrow retrieval before ranking. Without it, "3M capital expenditure
FY2018" returned "context does not provide": all 28 MMM filings carry
near-identical PP&E cash-flow rows, and nothing tied "FY2018" to the 10-K
filed 2019-02-07, so 2022-2023 look-alikes crowded it out of the top 5.

Deliberately conservative: when unsure (no match, two companies, ambiguous
word), return no filter -- a wrong filter hides the right answer, which is
worse than today's unfiltered search.
"""
from __future__ import annotations

import re
from typing import Any

# Only unambiguous names. Deliberately absent as bare words: "target", "block",
# "ups", "square" -- ordinary English that would create false filters.
COMPANY_NAMES: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvidia",), "AAPL": ("apple",), "MSFT": ("microsoft",),
    "GOOGL": ("alphabet", "google"), "META": ("meta platforms", "facebook"),
    "TSLA": ("tesla",), "F": ("ford", "ford motor"), "GM": ("general motors",),
    "RIVN": ("rivian",), "LCID": ("lucid",),
    "JPM": ("jpmorgan", "jp morgan", "j.p. morgan"), "BAC": ("bank of america",),
    "GS": ("goldman sachs", "goldman"), "MS": ("morgan stanley",), "V": ("visa",),
    "JNJ": ("johnson & johnson", "johnson and johnson"), "PFE": ("pfizer",),
    "UNH": ("unitedhealth", "united health"), "ABBV": ("abbvie",), "MRK": ("merck",),
    "XOM": ("exxon", "exxonmobil", "exxon mobil"), "CVX": ("chevron",),
    "COP": ("conocophillips",), "SLB": ("schlumberger",), "OXY": ("occidental",),
    "WMT": ("walmart", "wal-mart"), "COST": ("costco",), "HD": ("home depot",),
    "TGT": ("target corporation", "target corp"), "LOW": ("lowe's", "lowes"),
    "BA": ("boeing",), "CAT": ("caterpillar",), "GE": ("general electric",),
    "HON": ("honeywell",), "UPS": ("united parcel service",),
    "T": ("at&t",), "VZ": ("verizon",), "TMUS": ("t-mobile", "t mobile"),
    "CMCSA": ("comcast",), "CHTR": ("charter communications",),
    "DIS": ("disney",), "NFLX": ("netflix",), "WBD": ("warner bros", "warner brothers"),
    "PARA": ("paramount",), "SPOT": ("spotify",),
    "AMD": ("advanced micro devices",), "INTC": ("intel",), "QCOM": ("qualcomm",),
    "TXN": ("texas instruments",), "AVGO": ("broadcom",),
    "MMM": ("3m",), "PEP": ("pepsico", "pepsi"), "AMCR": ("amcor",),
    "BBY": ("best buy",), "AXP": ("american express", "amex"),
    "MGM": ("mgm resorts",), "ULTA": ("ulta",), "ADBE": ("adobe",),
    "GLW": ("corning",), "CVS": ("cvs health",), "GIS": ("general mills",),
    "NKE": ("nike",), "AES": ("aes corporation",), "AMZN": ("amazon",),
    "AWK": ("american water works", "american water"),
    "SQ": ("block, inc", "block inc", "square inc"),
    "KO": ("coca-cola", "coca cola"), "LMT": ("lockheed martin", "lockheed"),
    "ATVI": ("activision",), "FL": ("foot locker",),
    "KHC": ("kraft heinz", "kraft"), "PYPL": ("paypal",),
}

_NAME_PATTERNS = [
    (ticker, re.compile(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])"))
    for ticker, names in COMPANY_NAMES.items()
    for name in names
]
# Single-letter tickers (F, V, T) are too easily abbreviations -- name only.
_TICKER_TOKENS = {t for t in COMPANY_NAMES if len(t) >= 2}
_UPPER_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}(?![A-Za-z0-9])")

_FY_SHORT = re.compile(r"\bFY\s?(\d{2})\b", re.IGNORECASE)
# 19xx/20xx not glued to other digits, commas, decimals or a currency sign,
# so "$1577" or "12,018" never read as years.
_YEAR = re.compile(r"(?<![\d,.$])((?:19|20)\d{2})(?![\d,])")


def _extract_ticker(query: str) -> str | None:
    lowered = query.lower()
    found = {ticker for ticker, pattern in _NAME_PATTERNS if pattern.search(lowered)}
    found |= {tok for tok in _UPPER_TOKEN.findall(query) if tok in _TICKER_TOKENS}
    return found.pop() if len(found) == 1 else None


def _extract_years(query: str) -> tuple[int, int] | None:
    years = [int(y) for y in _YEAR.findall(query)]
    years += [2000 + int(y) for y in _FY_SHORT.findall(query)]
    return (min(years), max(years)) if years else None


def extract_filters(query: str) -> dict[str, Any]:
    """Return {"ticker": str | None, "years": (first, last) | None}."""
    return {"ticker": _extract_ticker(query), "years": _extract_years(query)}


def period_window(years: tuple[int, int]) -> tuple[str, str]:
    """Filing-date window (ISO strings) for questions about these fiscal years.

    Jan 1 of the first year through Dec 31 of the year after the last covers
    both Dec year-end filers (3M FY2018 10-K filed 2019-02) and Jan year-end
    filers (Walmart FY2018 10-K filed 2018-03) without a per-company calendar.
    """
    return f"{years[0]}-01-01", f"{years[1] + 1}-12-31"

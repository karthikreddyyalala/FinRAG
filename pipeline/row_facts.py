"""Turn each numeric row of a financial table into its own short, searchable fact.

A big table chunk dilutes the one row a question needs, so embeddings and
keyword search rank prose about the topic above the table holding the figure.
A fact like "MMM 10-K filed 2019-02-07: Purchases of PP&E: 2018: (1,577); ..."
puts the label, the filing and the values in one place.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_NUMBER = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?%?$")
_SKIP_LABEL = ("(millions", "(in millions", "years ended", "year ended", "fiscal year")


def _as_number(cell: str) -> float:
    return float(cell.strip("()%").replace(",", "") or 0)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")]


def _header_years(lines: list[str]) -> list[str]:
    for line in lines[:10]:
        years = [c for c in _cells(line) if _YEAR.match(c)]
        if len(years) >= 2:
            return list(dict.fromkeys(years))
    return []


def table_row_facts(text: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    """One fact per row that has a label and a value for every header year."""
    lines = text.splitlines()
    years = _header_years(lines)
    if not years:
        return []
    facts = []
    for line in lines:
        cells = _cells(line)
        label = next((c for c in cells if re.search(r"[A-Za-z]{3,}", c)), "")
        if not label or label.lower().startswith(_SKIP_LABEL):
            continue
        values = [c for c in cells if c != label and _NUMBER.match(c) and not _YEAR.match(c)]
        # Exactly one value per year, or the columns are not what the header
        # says (10-Q tables mix three-month and nine-month columns).
        if len(values) != len(years):
            continue
        # One number repeated under every year is a table-parsing artifact
        # (a spanning cell copied across columns), not a real time series.
        if len(years) > 1 and len({_as_number(v) for v in values}) == 1:
            continue
        pairs = "; ".join(f"{y}: {v}" for y, v in zip(years, values, strict=True))
        body = f"{meta['ticker']} {meta['filing_type']} filed {meta['period']}: {label}: {pairs}"
        facts.append({
            "chunk_id": "fact_" + hashlib.sha256(body.encode()).hexdigest()[:32],
            "text": body,
            "chunk_type": "fact",
            "section": "table_row",
            "page_number": None,
            "ticker": meta["ticker"],
            "filing_type": meta["filing_type"],
            "period": meta["period"],
        })
    return facts

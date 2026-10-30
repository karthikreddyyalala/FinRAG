"""Plan retrieval for derived-metric questions ("inventory turnover", "COGS % margin").

A ratio is not printed in any filing. Answering it takes several statement lines
(cost of sales AND inventories), but one search for the whole question surfaces
chunks about the topic and tends to find only one of the lines, so the answer
comes back "the context does not provide X". Each needed line is searched on its
own and given a guaranteed slot.
"""
from __future__ import annotations

import re
from typing import Any

# Lines each metric needs, named the way a filing names them.
RATIO_LINE_ITEMS: dict[str, tuple[str, ...]] = {
    "days payable outstanding": ("accounts payable", "cost of sales"),
    "dpo": ("accounts payable", "cost of sales"),
    "inventory turnover": ("cost of sales", "inventories"),
    "working capital": ("total current assets", "total current liabilities"),
    "current ratio": ("total current assets", "total current liabilities"),
    "quick ratio": (
        "cash and cash equivalents", "short-term investments", "accounts receivable",
        "total current liabilities",
    ),
    "gross margin": ("net sales", "cost of sales"),
    "cogs": ("net sales", "cost of sales"),
    "operating margin": ("operating income", "net sales"),
    "net margin": ("net income", "net sales"),
    "ebitda": ("operating income", "depreciation and amortization", "net sales"),
    "free cash flow": (
        "net cash provided by operating activities",
        "purchases of property, plant and equipment",
    ),
    "return on assets": ("net income", "total assets"),
    "roa": ("net income", "total assets"),
    "effective tax rate": ("provision for income taxes", "income before income taxes"),
    "dividend payout ratio": ("dividends", "net income"),
    "fixed asset turnover": ("net sales", "property, plant and equipment, net"),
    "operating cash flow ratio": (
        "net cash provided by operating activities", "total current liabilities",
    ),
}

_PATTERNS = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.IGNORECASE), items)
    for term, items in RATIO_LINE_ITEMS.items()
]


def line_items_for(query: str) -> list[str]:
    """Statement lines the metrics named in the query need, in order of mention."""
    found: list[tuple[int, tuple[str, ...]]] = []
    for pattern, items in _PATTERNS:
        match = pattern.search(query)
        if match:
            found.append((match.start(), items))
    ordered: list[str] = []
    for _, items in sorted(found, key=lambda f: f[0]):
        for item in items:
            if item not in ordered:
                ordered.append(item)
    return ordered


def add_per_item_winners(
    base: list[dict[str, Any]], winners: list[list[dict[str, Any]]], cap: int = 8
) -> list[dict[str, Any]]:
    """Append each line's best chunk not already present, up to cap chunks in all."""
    out = list(base)
    have = {c["chunk_id"] for c in out}
    for ranked in winners:
        if len(out) >= cap:
            break
        chosen = next((c for c in ranked if c["chunk_id"] not in have), None)
        if chosen is not None:
            out.append(chosen)
            have.add(chosen["chunk_id"])
    return out

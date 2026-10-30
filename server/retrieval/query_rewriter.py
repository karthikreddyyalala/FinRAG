"""Deterministic GAAP term expansion for retrieval.

The LLM rewrite step that used to live here was removed in M1: the MCP
client's own model now phrases the query (the tool arguments), and the
server runs no chat model.
"""
from __future__ import annotations

# Questions name a metric the way an analyst says it; filings label the same
# figure with its GAAP line item. "Capital expenditure" never appears in 3M's
# cash flow statement -- the line reads "Purchases of property, plant and
# equipment (PP&E)". With no term in common, BM25 cannot match it and the
# number table embeds too weakly for dense search to recover it, so the one
# chunk holding the answer is unreachable. Appending the filing's own wording
# is what puts it back in range.
GAAP_SYNONYMS = {
    "capital expenditure": "purchases of property plant and equipment PP&E capital spending",
    "capital expenditures": "purchases of property plant and equipment PP&E capital spending",
    "capex": "purchases of property plant and equipment PP&E capital spending",
    "revenue": "net sales total revenues",
    "top line": "net sales total revenues",
    "cogs": "cost of sales cost of goods sold",
    "cost of goods sold": "cost of sales",
    "gross margin": "gross profit net sales cost of sales",
    "operating margin": "operating income net sales",
    "net margin": "net income net sales",
    "ebitda": "operating income depreciation and amortization",
    "free cash flow": (
        "net cash provided by operating activities purchases of property plant and equipment"
    ),
    "operating cash flow": "net cash provided by operating activities",
    "inventory turnover": "cost of sales inventories",
    "dpo": "accounts payable cost of sales",
    "days payable outstanding": "accounts payable cost of sales",
    "working capital": "total current assets total current liabilities",
    "quick ratio": "cash and cash equivalents accounts receivable total current liabilities",
    "roa": "net income total assets",
    "return on assets": "net income total assets",
    "effective tax rate": "provision for income taxes income before income taxes",
    "dividend": "dividends paid to shareholders cash dividends",
    "eps": "earnings per share",
    "fixed asset turnover": "net sales property plant and equipment net",
}


def expand_financial_terms(query: str) -> str:
    """Append GAAP line-item phrasing for any metric named in the query.

    Args:
        query: The user's question, or the LLM-rewritten form of it.

    Returns:
        The query unchanged when it names no known metric, or already uses
        the filing's wording; otherwise the query plus the GAAP phrasing.
    """
    lowered = query.lower()
    additions: list[str] = []
    for term, expansion in GAAP_SYNONYMS.items():
        if term not in lowered:
            continue
        # Skip when the query already speaks the filing's language -- piling on
        # duplicate terms only dilutes the rest of the query.
        head = expansion.split()[0]
        if head in lowered:
            continue
        additions.append(expansion)

    if not additions:
        return query
    return f"{query} {' '.join(dict.fromkeys(additions))}"

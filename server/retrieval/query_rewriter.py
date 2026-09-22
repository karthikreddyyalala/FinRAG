"""Query rewriting via Claude Haiku on Bedrock: expand tickers, extract dates.

Uses a cross-region inference profile ID (the `us.` prefix), not the bare
`anthropic.claude-*` model ID -- Claude Haiku 4.5 rejects on-demand
invocation without it (verified against AWS Bedrock docs).
"""
from __future__ import annotations

import socket
from typing import Any

import botocore.exceptions

HAIKU_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

SYSTEM_PROMPT = (
    "Expand ticker symbols to company names. Extract time constraints. "
    "Optimize for financial document retrieval. Return rewritten query only."
)


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


def _is_bedrock_unavailable(exc: Exception) -> bool:
    """True when Bedrock is throttling, unreachable, or not enabled here.

    Kept in sync with the identical check in answer_generator.py (deliberately
    duplicated rather than imported across module boundaries -- see that
    module's comment). A plain network ReadTimeoutError took down a
    150-question eval run because timeout/connection faults are real
    botocore/socket exception types, not phrases in the message, and the
    text-only check did not catch them.
    """
    timeout_types = (
        botocore.exceptions.ReadTimeoutError
        | botocore.exceptions.ConnectTimeoutError
        | botocore.exceptions.EndpointConnectionError
        | socket.timeout
    )
    if isinstance(exc, timeout_types):
        return True
    text = str(exc)
    return (
        "Throttling" in text
        or "throttl" in text.lower()
        or "ResourceNotFoundException" in text
    )


def _rewrite_openai(query: str) -> str:
    """Rewrite via OpenAI, the fallback when Bedrock is unavailable.

    This is itself the last line of defense for every single question, so a
    transient connection error here must be retried, not just re-raised --
    the equivalent gap in answer_generator.py's fallback killed a
    150-question eval run at the very last question.
    """
    import os
    import time

    import openai
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    for attempt in range(8):
        try:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
            )
            return r.choices[0].message.content.strip()
        except Exception as oe:
            retriable = (
                isinstance(oe, openai.APIConnectionError | openai.APITimeoutError)
                or "429" in str(oe)
                or "rate_limit" in str(oe).lower()
            )
            if retriable:
                wait = 15 * (attempt + 1)
                print(f"    [{type(oe).__name__}] waiting {wait}s ...", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("OpenAI fallback: exhausted retries")


def rewrite_query(bedrock_client: Any, query: str) -> str:
    """Rewrite a user query for better financial document retrieval.

    Expands tickers and time constraints via the LLM, then appends GAAP
    line-item phrasing. The LLM rewrite alone preserves the analyst's
    vocabulary ("capital expenditure"), which is not the vocabulary the
    filing uses, so the deterministic expansion runs on top of it.

    Falls back to OpenAI gpt-4o-mini if Bedrock is throttled.
    """
    try:
        response = bedrock_client.converse(
            modelId=HAIKU_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": query}]}],
            inferenceConfig={"temperature": 0},
        )
        rewritten = response["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        if not _is_bedrock_unavailable(e):
            raise
        rewritten = _rewrite_openai(query)

    return expand_financial_terms(rewritten)

"""Bedrock Sonnet Converse API generation with mandatory inline citations.

Uses a cross-region inference profile ID (the `us.` prefix) -- same
requirement as query_rewriter.py's Haiku call, verified against AWS
Bedrock docs this session.

Citation-format/grounding instructions live in the system prompt (stable
across calls); retrieved context + the query live in the user message
(varies per call). This split is deliberate, not incidental -- Week 4
wires up Bedrock prompt caching, which only pays off when the system
prompt prefix stays identical call to call. Interpolating the
per-query context into system (as an earlier draft of this module did)
would defeat that caching entirely.
"""
from __future__ import annotations

import socket
from typing import Any

import botocore.exceptions

SONNET_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Grounding is the hard rule; the equivalence and sign guidance exist because
# without them the model refuses figures it has actually found. On
# FinanceBench Q1 it retrieved "Purchases of property, plant and equipment
# (PP&E) $(1,577)" and still answered that it could not determine capital
# expenditure -- they are the same line item, and the parentheses are the
# accounting sign convention, not part of the value.
SYSTEM_PROMPT_TEMPLATE = """Answer the question using only the provided context.

Grounding rules:
- Never state a number that does not appear verbatim in the context.
- If the context genuinely lacks the figure, say so. Do not guess.
- Cite every claim inline, e.g. {example_citation}

Reading financial statements:
- Filings label figures with their GAAP line item, not the analyst's term for
  them. Treat these as the same figure and answer directly:
    capital expenditures  = "Purchases of property, plant and equipment (PP&E)"
    revenue / top line    = "Net sales" / "Total revenues"
    COGS                  = "Cost of sales"
    operating cash flow   = "Net cash provided by operating activities"
- Parentheses around a number denote a negative or a cash outflow. For a
  question asking "how much was spent", report the magnitude: $(1,577) in a
  cash flow statement means $1,577 million of spending.
- Report the figure in the units the question asks for, converting between
  millions and billions where the context states its own units."""

USER_MESSAGE_TEMPLATE = """Context:
{context}

Question: {query}"""


def _is_bedrock_unavailable(exc: Exception) -> bool:
    """True when Bedrock is throttling, unreachable, or not enabled here.

    A 150-question eval run died on a plain network ReadTimeoutError with
    99/150 already checkpointed. Throttling and missing-model text checks
    caught quota faults but not transient network faults -- those are real
    botocore/socket exception types, not phrases in the message -- so a
    single slow request took down the whole process instead of falling
    back to OpenAI the way a throttle already did.
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


def format_citation(chunk: dict[str, Any]) -> str:
    """Format a chunk's metadata as a CLAUDE.md-style inline citation.

    Args:
        chunk: A chunk dict with ticker, filing_type, period, page_number.

    Returns:
        "[TICKER FILING_TYPE PERIOD p.N]", or without the page segment if
        page_number is None (HTML filings have no native pagination).
    """
    base = f"[{chunk['ticker']} {chunk['filing_type']} {chunk['period']}"
    if chunk.get("page_number") is not None:
        return f"{base} p.{chunk['page_number']}]"
    return f"{base}]"


# temperature=0 on every call in this module and in query_rewriter.py.
# Without it, the same question through the identical pipeline produced a
# correct, cited answer on one run and "the context does not provide this
# figure" on the next -- financial extraction has one right answer, and
# nothing here should be creative.
def generate_answer(
    bedrock_client: Any, query: str, chunks: list[dict[str, Any]]
) -> str:
    """Generate a cited answer from the top reranked chunks.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        query: The original user query.
        chunks: Top chunks from reranker.rerank(), each with text + citation
            metadata (ticker, filing_type, period, page_number).

    Returns:
        The generated answer text with inline citations.
    """
    context_blocks = [
        f"{chunk['text']}\nCitation: {format_citation(chunk)}" for chunk in chunks
    ]
    example_citation = format_citation(chunks[0]) if chunks else "[TICKER 10-Q PERIOD]"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(example_citation=example_citation)
    user_message = USER_MESSAGE_TEMPLATE.format(
        context="\n\n".join(context_blocks), query=query
    )

    def _call_openai() -> str:
        import os
        import time

        from openai import OpenAI

        openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        for attempt in range(8):
            try:
                r = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
                return r.choices[0].message.content
            except Exception as oe:
                if "429" in str(oe) or "rate_limit" in str(oe).lower():
                    wait = 15 * (attempt + 1)
                    print(f"    [rate limit] waiting {wait}s ...", flush=True)
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("OpenAI rate limit: exhausted retries")

    try:
        response = bedrock_client.converse(
            modelId=SONNET_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"temperature": 0},
        )
        return response["output"]["message"]["content"][0]["text"]
    except Exception as e:
        if _is_bedrock_unavailable(e):
            return _call_openai()
        raise

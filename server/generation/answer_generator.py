"""Bedrock Converse API generation with mandatory inline citations.

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

C5 (CLAUDE.md Phase C, model tier routing): generate_answer() takes a
`model` tier ("sonnet" or "haiku") rather than always using Sonnet.
get_company_financials (a single ticker/metric/period lookup -- CLAUDE.md's
"simple single-metric" case) routes to Haiku; search_sec_filings and
compare_companies (free-text and multi-hop respectively -- the "complex
comparison" case) stay on Sonnet.
"""
from __future__ import annotations

import socket
from typing import Any

import botocore.exceptions

from server.retrieval.query_rewriter import HAIKU_MODEL_ID

SONNET_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
MODEL_IDS = {"sonnet": SONNET_MODEL_ID, "haiku": HAIKU_MODEL_ID}

# chunker.py targets ~1500 words (~8000 chars) for a parent text chunk, but a
# table chunk is exempt from that target -- CLAUDE.md's chunker stores "each
# table as one chunk" regardless of size. A large schedule table (hundreds of
# rows) can run to tens of thousands of characters, and BM25-only retrieval
# (no dense/rerank pass to screen it out) surfaced one that blew Sonnet's
# context window outright: caught live on the FinanceBench 150 Baseline B
# run, question 91/150, "Input is too long for requested model." Cap here,
# not per-mode, since any retrieval path can hand generate_answer an
# oversized chunk.
MAX_CHUNK_CHARS = 8000

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
- Cite every claim inline, e.g. [MMM 10-K FY2018 p.40]

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


def _truncate(text: str) -> str:
    """Cap a single chunk's text so no oversized chunk can blow the model's
    context window on its own. See MAX_CHUNK_CHARS for why this exists."""
    if len(text) <= MAX_CHUNK_CHARS:
        return text
    return text[:MAX_CHUNK_CHARS] + "\n[... truncated]"


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
    bedrock_client: Any, query: str, chunks: list[dict[str, Any]], model: str = "sonnet"
) -> str:
    """Generate a cited answer from the top reranked chunks.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        query: The original user query.
        chunks: Top chunks from reranker.rerank(), each with text + citation
            metadata (ticker, filing_type, period, page_number).
        model: "sonnet" (default) or "haiku" -- see MODEL_IDS. Callers pick
            the tier; this function does not infer complexity on its own.

    Returns:
        The generated answer text with inline citations.

    Raises:
        ValueError: model is not one of MODEL_IDS' keys.
    """
    if model not in MODEL_IDS:
        raise ValueError(f"unknown model {model!r}; expected one of {sorted(MODEL_IDS)}")

    context_blocks = [
        f"{_truncate(chunk['text'])}\nCitation: {format_citation(chunk)}" for chunk in chunks
    ]

    # A fixed worked example, not chunks[0]'s own citation: prompt caching
    # (see SYSTEM_PROMPT_TEMPLATE's docstring) only pays off if this string
    # is byte-identical across calls. Interpolating a per-query citation
    # here made every "cacheable" prefix unique in practice.
    system_prompt = SYSTEM_PROMPT_TEMPLATE
    user_message = USER_MESSAGE_TEMPLATE.format(
        context="\n\n".join(context_blocks), query=query
    )

    def _call_openai() -> str:
        import os
        import time

        import openai
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
                # This is the fallback path itself -- if it also gives up, the
                # question fails outright. A transient network blip here
                # killed a 150-question run at question 150 of 150 because
                # only rate-limit text was retried, not connection errors.
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

    try:
        response = bedrock_client.converse(
            modelId=MODEL_IDS[model],
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"temperature": 0},
        )
        return response["output"]["message"]["content"][0]["text"]
    except Exception as e:
        if _is_bedrock_unavailable(e):
            return _call_openai()
        raise

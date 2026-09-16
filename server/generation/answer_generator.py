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

from typing import Any

SONNET_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

SYSTEM_PROMPT_TEMPLATE = """Cite every claim with the exact citation format shown below.
Never state a number not present verbatim in the provided context.
If context is insufficient, say so explicitly. Do not guess.
Format citations inline as shown, e.g. {example_citation}"""

USER_MESSAGE_TEMPLATE = """Context:
{context}

Question: {query}"""


def _is_bedrock_unavailable(exc: Exception) -> bool:
    """True when Bedrock is throttling or the model is not enabled on this account."""
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
        )
        return response["output"]["message"]["content"][0]["text"]
    except Exception as e:
        if _is_bedrock_unavailable(e):
            return _call_openai()
        raise

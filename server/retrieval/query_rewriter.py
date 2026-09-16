"""Query rewriting via Claude Haiku on Bedrock: expand tickers, extract dates.

Uses a cross-region inference profile ID (the `us.` prefix), not the bare
`anthropic.claude-*` model ID -- Claude Haiku 4.5 rejects on-demand
invocation without it (verified against AWS Bedrock docs).
"""
from __future__ import annotations

from typing import Any

HAIKU_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

SYSTEM_PROMPT = (
    "Expand ticker symbols to company names. Extract time constraints. "
    "Optimize for financial document retrieval. Return rewritten query only."
)


def _is_bedrock_unavailable(exc: Exception) -> bool:
    """True when Bedrock is throttling or the model is not enabled on this account."""
    text = str(exc)
    return (
        "Throttling" in text
        or "throttl" in text.lower()
        or "ResourceNotFoundException" in text
    )


def _rewrite_openai(query: str) -> str:
    import os

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    )
    return r.choices[0].message.content.strip()


def rewrite_query(bedrock_client: Any, query: str) -> str:
    """Rewrite a user query for better financial document retrieval.

    Falls back to OpenAI gpt-4o-mini if Bedrock is throttled.
    """
    try:
        response = bedrock_client.converse(
            modelId=HAIKU_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": query}]}],
        )
        return response["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        if _is_bedrock_unavailable(e):
            return _rewrite_openai(query)
        raise

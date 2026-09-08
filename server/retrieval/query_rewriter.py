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


def rewrite_query(bedrock_client: Any, query: str) -> str:
    """Rewrite a user query for better financial document retrieval.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        query: The original user query.

    Returns:
        The rewritten query text.
    """
    response = bedrock_client.converse(
        modelId=HAIKU_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": query}]}],
    )
    return response["output"]["message"]["content"][0]["text"].strip()

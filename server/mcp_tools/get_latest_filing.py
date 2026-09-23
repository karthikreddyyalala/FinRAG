"""get_latest_filing MCP tool: metadata lookup + brief summary (Week 5).

Per CLAUDE.md Tool 4 spec: "metadata lookup + brief summarization, no full
RAG pipeline". Metadata comes straight from EDGAR (live, authoritative --
the corpus can lag it by up to a week between refresh crons); the summary is
one cheap Haiku call over whatever corpus chunks already exist for that
company, not the four-stage rewrite/hybrid/rerank/verify pipeline the other
three tools run.
"""
from __future__ import annotations

import socket
from dataclasses import asdict
from typing import Any

import botocore.exceptions
from mcp.server import MCPServer

from pipeline.edgar_client import get_cik_for_ticker, list_filings
from server.retrieval.query_rewriter import HAIKU_MODEL_ID

NOT_INGESTED_MESSAGE = (
    "No summary available -- this filing has not yet been ingested into the corpus."
)

SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following SEC filing excerpts in exactly 3 sentences. "
    "Be concrete and specific. Do not speculate beyond what the excerpts say."
)


def _is_bedrock_unavailable(exc: Exception) -> bool:
    """True when Bedrock is throttling, unreachable, or not enabled here.

    Kept in sync with the identical check in query_rewriter.py and
    answer_generator.py (deliberately duplicated, not imported -- see
    those modules' comments). Every other LLM call site in this codebase
    already fell back to OpenAI after being burned by exactly this
    failure mode killing a live run.
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


def _call_openai_summary(ticker: str, filing_type: str, context: str) -> str:
    import os

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"{ticker} {filing_type}:\n\n{context}"},
        ],
    )
    return r.choices[0].message.content.strip()


def _summarize(bedrock_client: Any, ticker: str, filing_type: str, chunks: list[dict]) -> str:
    if not chunks:
        return NOT_INGESTED_MESSAGE

    context = "\n\n".join(c.get("text", "") for c in chunks)
    user_text = f"{ticker} {filing_type}:\n\n{context}"
    try:
        response = bedrock_client.converse(
            modelId=HAIKU_MODEL_ID,
            system=[{"text": SUMMARY_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"temperature": 0},
        )
        return response["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        if not _is_bedrock_unavailable(e):
            raise
        return _call_openai_summary(ticker, filing_type, context)


def build_latest_filing_answer(
    ticker: str,
    filing_type: str,
    bedrock_client: Any,
    keyword_index: Any,
) -> dict[str, Any]:
    """Look up a company's most recent filing of a given type, with a brief summary.

    Args:
        ticker: Company ticker, e.g. "AAPL".
        filing_type: SEC form type, e.g. "10-Q" or "10-K".
        bedrock_client: A boto3 bedrock-runtime client (Haiku only).
        keyword_index: sync_pinecone.KeywordIndex over the full corpus.

    Returns:
        {"filing": {ticker, cik, form_type, filing_date, accession_number,
        primary_document}, "summary": str}

    Raises:
        ValueError: If EDGAR has no filing of this type for this ticker.
    """
    cik = get_cik_for_ticker(ticker)
    filings = list_filings(ticker, cik, form_limits={filing_type: 1})
    if not filings:
        raise ValueError(f"No {filing_type} filings found for {ticker!r} on EDGAR")
    filing = filings[0]

    chunks = keyword_index.search(f"{ticker} {filing_type}", top_k=5)
    summary = _summarize(bedrock_client, ticker, filing_type, chunks)

    return {"filing": asdict(filing), "summary": summary}


def register_get_latest_filing_tool(
    mcp: MCPServer,
    bedrock_client: Any,
    keyword_index: Any,
) -> None:
    """Register the get_latest_filing tool on an MCPServer instance."""

    @mcp.tool()
    def get_latest_filing(ticker: str, filing_type: str) -> dict[str, Any]:
        """Get metadata and a brief summary of a company's most recent filing.

        Args:
            ticker: Company ticker, e.g. "AAPL".
            filing_type: SEC form type, e.g. "10-Q" or "10-K".

        Returns:
            Dict with filing metadata and a 3-sentence summary.
        """
        return build_latest_filing_answer(ticker, filing_type, bedrock_client, keyword_index)

"""get_company_financials MCP tool: targeted single-metric lookup (Week 5).

Unlike search_sec_filings, the input is already structured (ticker, metric,
period) -- there is no natural-language phrasing for Haiku to expand, so
this skips straight to the deterministic GAAP expansion + hybrid search +
rerank + verify stages.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from server.generation.answer_generator import generate_answer
from server.retrieval.hybrid_retriever import hybrid_search
from server.retrieval.numerical_verifier import verify_answer
from server.retrieval.query_filters import extract_filters, period_window
from server.retrieval.query_rewriter import expand_financial_terms
from server.retrieval.reranker import rerank


def build_financials_answer(
    ticker: str,
    metric: str,
    period: str,
    bedrock_client: Any,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Look up a single metric for a company/period and return a cited value.

    Args:
        ticker: Company ticker, e.g. "NVDA".
        metric: Metric name, e.g. "revenue" or "capital expenditure".
        period: Reporting period, e.g. "Q1-2026".
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        keyword_index: sync_pinecone.KeywordIndex over the full corpus.
        embed_fn: Callable(text) -> embedding vector.
        top_k: Number of chunks to keep after reranking.

    Returns:
        {"ticker", "metric", "period", "answer", "citations", "cost_usd", "latency_ms"}
    """
    start = time.monotonic()

    query = f"What was {ticker}'s {metric} for {period}?"
    lexical_query = expand_financial_terms(f"{ticker} {metric} {period}")

    years = extract_filters(period)["years"]
    candidates = hybrid_search(
        lexical_query, keyword_index, pinecone_index, embed_fn,
        ticker=ticker.upper(),
        period_range=period_window(years) if years else None,
    )
    # The ticker is a known input here, unlike search_sec_filings' free-text
    # queries -- a short ticker like "F" is too weak a lexical signal for
    # BM25/dense retrieval to reliably constrain to the right company, so an
    # unrelated chunk from another ticker can ride along in the candidate
    # set. Filtering by the metadata we already have is cheap and exact.
    own_ticker_candidates = [c for c in candidates if c.get("ticker", "").upper() == ticker.upper()]
    top_chunks = rerank(query, own_ticker_candidates, top_k=top_k, lexical_query=lexical_query)

    raw_answer = generate_answer(bedrock_client, query, top_chunks)
    source_texts = [chunk["text"] for chunk in top_chunks]
    verified_answer = verify_answer(raw_answer, source_texts)

    citations = [
        {
            "ticker": chunk.get("ticker"),
            "filing_type": chunk.get("filing_type"),
            "period": chunk.get("period"),
            "page": chunk.get("page_number"),
            "text": chunk.get("text", ""),
        }
        for chunk in top_chunks
    ]

    return {
        "ticker": ticker,
        "metric": metric,
        "period": period,
        "answer": verified_answer,
        "citations": citations,
        "cost_usd": 0.0,
        "latency_ms": int((time.monotonic() - start) * 1000),
    }


def register_get_financials_tool(
    mcp: MCPServer,
    bedrock_client: Any,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
) -> None:
    """Register the get_company_financials tool on an MCPServer instance."""

    @mcp.tool()
    def get_company_financials(ticker: str, metric: str, period: str) -> dict[str, Any]:
        """Look up a specific financial metric for a company and period.

        Args:
            ticker: Company ticker, e.g. "NVDA".
            metric: Metric name, e.g. "revenue", "capital expenditure", "gross margin".
            period: Reporting period, e.g. "Q1-2026" or "FY2018".

        Returns:
            Dict with ticker, metric, period, answer, citations, cost_usd, latency_ms.
        """
        return build_financials_answer(
            ticker, metric, period, bedrock_client, pinecone_index, keyword_index, embed_fn
        )

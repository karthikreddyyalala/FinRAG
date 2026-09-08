"""search_sec_filings MCP tool: direct Pinecone query, no reranking (Week 1).

Week 2 adds query rewriting, hybrid BM25+dense search, CrossEncoder
reranking, and the numerical verifier per CLAUDE.md's build order. This
tool proves the retrieval -> citation plumbing works end to end first.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer


def build_search_filings_answer(
    query: str,
    pinecone_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Run a direct Pinecone similarity search and format a cited answer.

    Args:
        query: Natural language financial question.
        pinecone_index: A Pinecone Index handle.
        embed_fn: Callable(text) -> embedding vector, embeds the query.
        top_k: Number of chunks to retrieve.

    Returns:
        {"answer": str, "citations": [...], "cost_usd": float, "latency_ms": int}
    """
    start = time.monotonic()
    query_vector = embed_fn(query)
    results = pinecone_index.query(vector=query_vector, top_k=top_k, include_metadata=True)

    citations = []
    passages = []
    for match in results["matches"]:
        meta = match["metadata"]
        citations.append(
            {
                "ticker": meta.get("ticker"),
                "filing_type": meta.get("filing_type"),
                "period": meta.get("period"),
                "page": meta.get("page_number"),
            }
        )
        passages.append(meta.get("text", ""))

    answer = (
        "Retrieved passages (Week 1: raw retrieval, no generation model yet):\n\n"
        + "\n---\n".join(passages)
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "answer": answer,
        "citations": citations,
        "cost_usd": 0.0,
        "latency_ms": latency_ms,
    }


def register_search_filings_tool(
    mcp: MCPServer, pinecone_index: Any, embed_fn: Callable[[str], list[float]]
) -> None:
    """Register the search_sec_filings tool on an MCPServer instance.

    Args:
        mcp: The MCPServer instance to register the tool on.
        pinecone_index: A Pinecone Index handle used at query time.
        embed_fn: Callable(text) -> embedding vector for embedding queries.
    """

    @mcp.tool()
    def search_sec_filings(query: str) -> dict[str, Any]:
        """Search ingested SEC filings and return a cited answer.

        Args:
            query: Natural language financial question, e.g. "How did
                Nvidia data center revenue change from Q1 2024 to Q1 2026?"

        Returns:
            Dict with answer text, citations, cost_usd, and latency_ms.
        """
        return build_search_filings_answer(query, pinecone_index, embed_fn)

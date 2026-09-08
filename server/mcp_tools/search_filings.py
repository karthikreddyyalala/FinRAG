"""search_sec_filings MCP tool: full retrieval pipeline (Week 2).

rewrite -> hybrid search -> rerank -> generate -> verify, per CLAUDE.md's
query flow. Replaces Week 1's direct-Pinecone-only version.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from rank_bm25 import BM25Okapi

from server.generation.answer_generator import generate_answer
from server.retrieval.hybrid_retriever import hybrid_search
from server.retrieval.numerical_verifier import verify_answer
from server.retrieval.query_rewriter import rewrite_query
from server.retrieval.reranker import rerank


def build_search_filings_answer(
    query: str,
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Run the full four-stage retrieval pipeline and format a cited answer.

    Args:
        query: Natural language financial question.
        bedrock_client: A boto3 bedrock-runtime client (used for rewrite,
            generation, and -- via embed_fn's closure -- embeddings).
        pinecone_index: A Pinecone Index handle.
        bm25_index: The corpus-wide BM25 index from sync_pinecone.load_bm25_index().
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector, for the Pinecone query.
        top_k: Number of chunks to keep after reranking.

    Returns:
        {"answer": str, "citations": [...], "cost_usd": float, "latency_ms": int}
    """
    start = time.monotonic()

    rewritten = rewrite_query(bedrock_client, query)
    candidates = hybrid_search(rewritten, bm25_index, bm25_chunks, pinecone_index, embed_fn)
    top_chunks = rerank(query, candidates, top_k=top_k)

    raw_answer = generate_answer(bedrock_client, query, top_chunks)
    source_texts = [chunk["text"] for chunk in top_chunks]
    verified_answer = verify_answer(raw_answer, source_texts)

    citations = [
        {
            "ticker": chunk.get("ticker"),
            "filing_type": chunk.get("filing_type"),
            "period": chunk.get("period"),
            "page": chunk.get("page_number"),
        }
        for chunk in top_chunks
    ]

    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "answer": verified_answer,
        "citations": citations,
        "cost_usd": 0.0,  # Week 4 wires real per-stage cost tracking
        "latency_ms": latency_ms,
    }


def register_search_filings_tool(
    mcp: MCPServer,
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
) -> None:
    """Register the search_sec_filings tool on an MCPServer instance.

    Args:
        mcp: The MCPServer instance to register the tool on.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        bm25_index: The corpus-wide BM25 index.
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector.
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
        return build_search_filings_answer(
            query, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
        )

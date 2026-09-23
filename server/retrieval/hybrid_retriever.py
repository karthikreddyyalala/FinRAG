"""Parallel BM25 keyword search + Pinecone dense search, merged and deduped."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from typing import Any


def _normalize_pinecone_match(match: dict[str, Any]) -> dict[str, Any]:
    chunk = dict(match.get("metadata") or {})
    chunk["chunk_id"] = match["id"]
    return chunk


def merge_and_dedup(
    bm25_chunks: list[dict[str, Any]], pinecone_matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge BM25 and Pinecone results, deduplicating by chunk_id.

    Args:
        bm25_chunks: Results from KeywordIndex.search() (already chunk-shaped).
        pinecone_matches: Raw matches from pinecone_index.query()["matches"]
            (each a {"id", "metadata"} dict, normalized here to chunk shape).

    Returns:
        Deduplicated chunks interleaved by rank (BM25 #1, dense #1, BM25 #2,
        ...). Interleaving -- rather than concatenating -- is load-bearing:
        downstream rerank() truncates to top_k, so a concatenated list would
        drop every dense result whenever BM25 alone fills the slice.
    """
    normalized_pinecone = [_normalize_pinecone_match(m) for m in pinecone_matches]
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for pair in zip_longest(bm25_chunks, normalized_pinecone):
        for chunk in pair:
            if chunk is None:
                continue
            chunk_id = chunk["chunk_id"]
            if chunk_id not in seen:
                seen.add(chunk_id)
                merged.append(chunk)
    return merged


def hybrid_search(
    rewritten_query: str,
    keyword_index: Any,
    pinecone_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Run BM25 and Pinecone search in parallel, merge and dedup the results.

    Args:
        rewritten_query: The query text from query_rewriter.rewrite_query().
        keyword_index: A sync_pinecone.KeywordIndex (SQLite FTS5, BM25-ranked).
        pinecone_index: A Pinecone Index handle.
        embed_fn: Callable(text) -> embedding vector, for the Pinecone query.
        top_k: Number of results to take from each source before merging.

    Returns:
        Up to 2*top_k deduplicated candidate chunks.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        bm25_future = executor.submit(keyword_index.search, rewritten_query, top_k)
        pinecone_future = executor.submit(
            lambda: pinecone_index.query(
                vector=embed_fn(rewritten_query), top_k=top_k, include_metadata=True
            )["matches"]
        )
        bm25_results = bm25_future.result()
        pinecone_matches = pinecone_future.result()

    return merge_and_dedup(bm25_results, pinecone_matches)

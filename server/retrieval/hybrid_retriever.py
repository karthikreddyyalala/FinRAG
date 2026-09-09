"""Parallel BM25 keyword search + Pinecone dense search, merged and deduped."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rank_bm25 import BM25Okapi


def bm25_search(
    bm25_index: BM25Okapi, chunks: list[dict[str, Any]], query: str, top_k: int = 10
) -> list[dict[str, Any]]:
    """Rank chunks by BM25 keyword relevance to a query.

    Args:
        bm25_index: A BM25Okapi index built over `chunks`' text (same order).
        chunks: The chunks the index was built from.
        query: The search query.
        top_k: Number of top-scoring chunks to return.

    Returns:
        Up to top_k chunks, highest BM25 score first.
    """
    scores = bm25_index.get_scores(query.lower().split())
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [chunks[i] for i in ranked_idx]


def _normalize_pinecone_match(match: dict[str, Any]) -> dict[str, Any]:
    chunk = dict(match.get("metadata") or {})
    chunk["chunk_id"] = match["id"]
    return chunk


def merge_and_dedup(
    bm25_chunks: list[dict[str, Any]], pinecone_matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge BM25 and Pinecone results, deduplicating by chunk_id.

    Args:
        bm25_chunks: Results from bm25_search() (already chunk-shaped).
        pinecone_matches: Raw matches from pinecone_index.query()["matches"]
            (each a {"id", "metadata"} dict, normalized here to chunk shape).

    Returns:
        Deduplicated chunks, BM25 results first, then new Pinecone results,
        original relative order preserved within each source.
    """
    normalized_pinecone = [_normalize_pinecone_match(m) for m in pinecone_matches]
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for chunk in [*bm25_chunks, *normalized_pinecone]:
        chunk_id = chunk["chunk_id"]
        if chunk_id not in seen:
            seen.add(chunk_id)
            merged.append(chunk)
    return merged


def hybrid_search(
    rewritten_query: str,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    pinecone_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Run BM25 and Pinecone search in parallel, merge and dedup the results.

    Args:
        rewritten_query: The query text from query_rewriter.rewrite_query().
        bm25_index: A BM25Okapi index over the full corpus.
        bm25_chunks: The chunks bm25_index was built from.
        pinecone_index: A Pinecone Index handle.
        embed_fn: Callable(text) -> embedding vector, for the Pinecone query.
        top_k: Number of results to take from each source before merging.

    Returns:
        Up to 2*top_k deduplicated candidate chunks.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        bm25_future = executor.submit(
            bm25_search, bm25_index, bm25_chunks, rewritten_query, top_k
        )
        pinecone_future = executor.submit(
            lambda: pinecone_index.query(
                vector=embed_fn(rewritten_query), top_k=top_k, include_metadata=True
            )["matches"]
        )
        bm25_results = bm25_future.result()
        pinecone_matches = pinecone_future.result()

    return merge_and_dedup(bm25_results, pinecone_matches)

"""Rerank candidates from hybrid retrieval: top-N -> top-K by relevance.

Two backends. The CrossEncoder (cross-encoder/ms-marco-MiniLM-L-6-v2) is the
intended one and runs on Lambda. It is unusable on macOS + Python 3.13 --
torch deadlocks on a mutex during the first forward pass and never returns --
so a dependency-free lexical scorer takes over there.

Blind `chunks[:top_k]` truncation is NOT an acceptable fallback: hybrid_search
interleaves two differently-scaled score spaces (BM25 and cosine), so list
position alone does not encode cross-source relevance.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was were what when where which who will with".split()
)


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9$%.]+", text.lower()) if t not in _STOPWORDS}


def _lexical_score(query_terms: set[str], chunk_text: str) -> float:
    """Fraction of query terms present in the chunk (Jaccard-style overlap)."""
    if not query_terms:
        return 0.0
    return len(query_terms & _terms(chunk_text)) / len(query_terms)


@lru_cache(maxsize=1)
def _get_model():
    """Load the CrossEncoder once per process (Lambda warm start)."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(MODEL_NAME, device="cpu")


def _crossencoder_available() -> bool:
    import platform
    import sys

    if platform.system() == "Darwin" and sys.version_info >= (3, 13):
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def rerank(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    """Rerank candidate chunks by relevance to the query, keeping the top_k.

    Args:
        query: The ORIGINAL user query, not the rewritten one -- CrossEncoder
            is trained on natural-language queries.
        chunks: Candidates from hybrid_search(), interleaved across sources.
        top_k: How many chunks to keep.

    Returns:
        Up to top_k chunks, most relevant first.
    """
    if not chunks:
        return []

    if _crossencoder_available():
        try:
            model = _get_model()
            scores = model.predict([(query, c.get("text", "")) for c in chunks])
            ranked = sorted(zip(scores, chunks), key=lambda p: p[0], reverse=True)
            return [chunk for _, chunk in ranked[:top_k]]
        except Exception:
            pass  # fall through to the lexical scorer

    query_terms = _terms(query)
    ranked_lex = sorted(
        chunks, key=lambda c: _lexical_score(query_terms, c.get("text", "")), reverse=True
    )
    return ranked_lex[:top_k]

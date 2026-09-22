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

import math
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


def _candidate_idf(query_terms: set[str], chunk_terms: list[set[str]]) -> dict[str, float]:
    """Weight each query term by how well it separates these candidates.

    Plain overlap counting rewards length: a long prose chunk picks up
    "company", "cash", "amount", "year" by chance and outscores the short
    table that actually holds the figure. Measured on FinanceBench Q1, an
    irrelevant LIBOR passage beat the correct cash-flow table 0.769 to 0.423.

    A term present in nearly every candidate carries no signal about which to
    pick, so it is damped; a term in only one or two is what distinguishes
    them. Computed over the candidate set rather than the corpus -- it needs
    no global statistics and adapts to whatever retrieval returned.
    """
    n = len(chunk_terms)
    idf: dict[str, float] = {}
    for term in query_terms:
        df = sum(1 for terms in chunk_terms if term in terms)
        idf[term] = math.log((n + 1) / (df + 1)) + 1.0
    return idf


# BM25's default length-normalisation strength. Weighting terms by rarity is
# not enough on its own: a long chunk still accumulates more matches purely by
# being long. On FinanceBench Q1 the correct table's terms were twice as
# discriminative (idf 2.39 vs ~1.5) yet it still lost 14.3 to 18.8 on raw
# count alone. Dividing by length is what makes a short, precise chunk win.
LENGTH_NORM_B = 0.75


def _lexical_score(
    query_terms: set[str],
    chunk_terms: set[str],
    idf: dict[str, float] | None = None,
    avg_len: float | None = None,
) -> float:
    """Score a chunk by its IDF-weighted, length-normalised term overlap.

    Args:
        query_terms: Content terms from the query.
        chunk_terms: Content terms of the candidate chunk.
        idf: Per-term weights from _candidate_idf(). Without it the score
            degrades to plain overlap, which favours verbose chunks.
        avg_len: Mean candidate length, for BM25-style normalisation.
    """
    if not query_terms:
        return 0.0
    matched = query_terms & chunk_terms
    if idf is None:
        return len(matched) / len(query_terms)

    total = sum(idf.get(t, 1.0) for t in query_terms)
    if not total:
        return 0.0
    score = sum(idf.get(t, 1.0) for t in matched) / total

    if avg_len:
        norm = 1 - LENGTH_NORM_B + LENGTH_NORM_B * (len(chunk_terms) / avg_len)
        if norm > 0:
            score /= norm
    return score


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


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 5,
    lexical_query: str | None = None,
) -> list[dict[str, Any]]:
    """Rerank candidate chunks by relevance to the query, keeping the top_k.

    Args:
        query: The ORIGINAL user query, not the rewritten one -- CrossEncoder
            is trained on natural-language queries.
        chunks: Candidates from hybrid_search(), interleaved across sources.
        top_k: How many chunks to keep.
        lexical_query: Query text for the lexical fallback only. Pass the
            GAAP-expanded form here: the fallback scores by term overlap, so
            on the natural query it would discard the very chunk dense search
            found -- "capital expenditure" shares no term with "Purchases of
            property, plant and equipment". CrossEncoder keeps using `query`,
            since it is trained on natural phrasing.

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

    query_terms = _terms(lexical_query or query)
    chunk_terms = [_terms(c.get("text", "")) for c in chunks]
    idf = _candidate_idf(query_terms, chunk_terms)
    avg_len = sum(len(t) for t in chunk_terms) / len(chunk_terms)

    scored = [
        (_lexical_score(query_terms, terms, idf, avg_len), i)
        for i, terms in enumerate(chunk_terms)
    ]
    scored.sort(key=lambda p: p[0], reverse=True)
    return [chunks[i] for _, i in scored[:top_k]]

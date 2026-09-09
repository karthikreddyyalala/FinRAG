"""CrossEncoder reranking: top-N candidates -> top-K by true relevance.

Deployed as a separate container-image Lambda (not the main zip-deployed
API Lambda) -- sentence-transformers + torch is ~1.2GB installed, well over
Lambda's 250MB zip limit. See the Task 9 deployment step for the container
packaging.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _get_model() -> CrossEncoder:
    """Load the CrossEncoder model once per process (Lambda warm start)."""
    return CrossEncoder(MODEL_NAME)


def rerank(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    """Rerank candidate chunks by true relevance to the query.

    Args:
        query: The original user query (not the rewritten one -- CrossEncoder
            models are trained on natural queries, not keyword-expanded ones).
        chunks: Candidate chunks from hybrid_retriever.hybrid_search().
        top_k: Number of top-ranked chunks to return.

    Returns:
        Up to top_k chunks, highest true-relevance score first.
    """
    model = _get_model()
    pairs = [(query, chunk["text"]) for chunk in chunks]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda pair: pair[0], reverse=True)
    return [chunk for _score, chunk in ranked[:top_k]]

"""TDD: hybrid merge + rerank must keep results from BOTH retrieval sources."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.retrieval.hybrid_retriever import merge_and_dedup
from server.retrieval.reranker import rerank


def _bm25(n=10):
    return [
        {"chunk_id": f"bm25-{i}", "text": f"bm25 chunk {i}", "source": "bm25"}
        for i in range(n)
    ]


def _pinecone_matches(n=10):
    return [
        {"id": f"dense-{i}", "metadata": {"text": f"dense chunk {i}", "source": "dense"}}
        for i in range(n)
    ]


def test_merged_topk_contains_both_sources():
    """Top-5 of merged results must include both BM25 and dense hits --
    otherwise half the retrieval stack is silently disabled."""
    merged = merge_and_dedup(_bm25(), _pinecone_matches())
    top = rerank("what was revenue", merged, top_k=5)

    assert len(top) == 5, f"expected 5 chunks, got {len(top)}"
    sources = {c["source"] for c in top}
    assert "dense" in sources, f"all dense results dropped; sources={sources}"
    assert "bm25" in sources, f"all bm25 results dropped; sources={sources}"


def test_merge_dedups_by_chunk_id():
    """A chunk present in both sources appears once."""
    bm25 = [{"chunk_id": "shared", "text": "x", "source": "bm25"}]
    dense = [{"id": "shared", "metadata": {"text": "x", "source": "dense"}}]
    merged = merge_and_dedup(bm25, dense)
    assert len(merged) == 1, f"expected dedup to 1, got {len(merged)}"


def test_lexical_rerank_can_use_expanded_query():
    """The lexical fallback scores by term overlap, so it must be able to see
    the GAAP phrasing. Otherwise it discards the very chunk dense search
    surfaced: a question says "capital expenditure", the filing says
    "Purchases of property, plant and equipment", and overlap is zero."""
    chunks = [
        {"chunk_id": "noise", "text": "deferred income taxes and other assets"},
        {
            "chunk_id": "correct",
            "text": "Purchases of property, plant and equipment (PP&E) $ (1,577)",
        },
    ]
    natural = "What is the FY2018 capital expenditure amount for 3M?"
    expanded = natural + " purchases of property plant and equipment PP&E"

    # Without the expansion the correct chunk has no terms in common.
    assert rerank(natural, chunks, top_k=1)[0]["chunk_id"] != "correct"

    # With it, the correct chunk ranks first.
    top = rerank(natural, chunks, top_k=1, lexical_query=expanded)
    assert top[0]["chunk_id"] == "correct", "expanded query did not reach the scorer"


def test_merge_handles_uneven_source_lengths():
    """Interleaving must not drop the tail of the longer source."""
    merged = merge_and_dedup(_bm25(3), _pinecone_matches(8))
    assert len(merged) == 11, f"expected all 11 chunks, got {len(merged)}"


if __name__ == "__main__":
    test_merged_topk_contains_both_sources()
    test_merge_dedups_by_chunk_id()
    test_merge_handles_uneven_source_lengths()
    print("PASS")

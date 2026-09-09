from unittest.mock import MagicMock

from rank_bm25 import BM25Okapi

from server.retrieval.hybrid_retriever import bm25_search, hybrid_search, merge_and_dedup


def _bm25_fixture():
    # A third, unrelated chunk is included so BM25's idf is meaningful: with
    # only 2 documents, any term unique to one document gets idf == 0 (df=1
    # cancels out under BM25Okapi's formula), so "data"/"center" would
    # contribute nothing and the shared word "revenue" alone (idf < 0,
    # favoring the longer document) would wrongly rank c2 above c1.
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew significantly"},
        {"chunk_id": "c2", "text": "Apple iPhone revenue declined slightly this quarter"},
        {"chunk_id": "c0", "text": "Tesla vehicle deliveries increased in the quarter"},
    ]
    tokenized = [c["text"].lower().split() for c in chunks]
    return BM25Okapi(tokenized), chunks


def test_bm25_search_returns_top_k_chunks_by_score():
    bm25, chunks = _bm25_fixture()

    results = bm25_search(bm25, chunks, "Nvidia data center revenue", top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"


def test_merge_and_dedup_removes_duplicate_chunk_ids():
    bm25_chunks = [{"chunk_id": "c1", "text": "a"}, {"chunk_id": "c2", "text": "b"}]
    pinecone_matches = [
        {"id": "c2", "metadata": {"text": "b"}},
        {"id": "c3", "metadata": {"text": "c"}},
    ]

    merged = merge_and_dedup(bm25_chunks, pinecone_matches)

    assert [c["chunk_id"] for c in merged] == ["c1", "c2", "c3"]


def test_normalize_pinecone_match_handles_missing_metadata():
    from server.retrieval.hybrid_retriever import _normalize_pinecone_match

    chunk = _normalize_pinecone_match({"id": "c1"})  # no "metadata" key at all

    assert chunk == {"chunk_id": "c1"}


def test_hybrid_search_runs_bm25_and_pinecone_in_parallel_and_merges():
    bm25, chunks = _bm25_fixture()
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {
        "matches": [{"id": "c3", "metadata": {"text": "Tesla margin fell"}}]
    }
    embed_fn = MagicMock(return_value=[0.1, 0.2])

    results = hybrid_search(
        rewritten_query="Nvidia data center revenue",
        bm25_index=bm25,
        bm25_chunks=chunks,
        pinecone_index=pinecone_index,
        embed_fn=embed_fn,
        top_k=10,
    )

    ids = {c["chunk_id"] for c in results}
    assert "c1" in ids  # from BM25
    assert "c3" in ids  # from Pinecone
    embed_fn.assert_called_once_with("Nvidia data center revenue")

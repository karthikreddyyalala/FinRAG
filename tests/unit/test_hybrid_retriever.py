from unittest.mock import MagicMock

from pipeline.sync_pinecone import KeywordIndex, build_keyword_index
from server.retrieval.hybrid_retriever import hybrid_search, merge_and_dedup


def _keyword_index(tmp_path):
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew significantly"},
        {"chunk_id": "c2", "text": "Apple iPhone revenue declined slightly this quarter"},
        {"chunk_id": "c0", "text": "Tesla vehicle deliveries increased in the quarter"},
    ]
    path = tmp_path / "kw.sqlite"
    build_keyword_index(path, iter(chunks))
    return KeywordIndex(path)


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


def test_hybrid_search_runs_bm25_and_pinecone_in_parallel_and_merges(tmp_path):
    keyword_index = _keyword_index(tmp_path)
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {
        "matches": [{"id": "c3", "metadata": {"text": "Tesla margin fell"}}]
    }
    embed_fn = MagicMock(return_value=[0.1, 0.2])

    results = hybrid_search(
        rewritten_query="Nvidia data center revenue",
        keyword_index=keyword_index,
        pinecone_index=pinecone_index,
        embed_fn=embed_fn,
        top_k=10,
    )

    ids = {c["chunk_id"] for c in results}
    assert "c1" in ids  # from BM25
    assert "c3" in ids  # from Pinecone
    embed_fn.assert_called_once_with("Nvidia data center revenue")

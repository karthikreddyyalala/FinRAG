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


def _pc_match(cid, ticker, period):
    return {"id": cid, "metadata": {"text": "PP&E", "ticker": ticker, "period": period}}


def test_filters_reach_both_sources_and_period_is_applied_to_dense_hits():
    """Pinecone metadata filters can't range-compare strings, so the ticker
    goes to Pinecone as a filter and the date window is applied afterwards."""
    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": [
        _pc_match("mmm-2019", "MMM", "2019-02-07"),
        _pc_match("mmm-2023", "MMM", "2023-02-08"),
    ]}

    results = hybrid_search("capex", keyword_index, pinecone_index, lambda t: [0.0],
                            ticker="MMM", period_range=("2018-01-01", "2019-12-31"))

    assert [c["chunk_id"] for c in results] == ["mmm-2019"]
    kw_kwargs = keyword_index.search.call_args.kwargs
    assert kw_kwargs["ticker"] == "MMM"
    assert kw_kwargs["period_range"] == ("2018-01-01", "2019-12-31")
    assert pinecone_index.query.call_args.kwargs["filter"] == {"ticker": {"$eq": "MMM"}}


def test_empty_filtered_result_falls_back_to_unfiltered_search():
    """A wrong filter must never be worse than no filter: if nothing
    survives, search again without it."""
    keyword_index = MagicMock()
    keyword_index.search.side_effect = [[], [{"chunk_id": "any", "text": "x"}]]
    pinecone_index = MagicMock()
    pinecone_index.query.side_effect = [{"matches": []}, {"matches": []}]

    results = hybrid_search("capex", keyword_index, pinecone_index, lambda t: [0.0],
                            ticker="MMM", period_range=("2018-01-01", "2019-12-31"))

    assert [c["chunk_id"] for c in results] == ["any"]
    assert "filter" not in pinecone_index.query.call_args_list[1].kwargs


def test_no_filters_sends_no_pinecone_filter():
    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    hybrid_search("capex", keyword_index, pinecone_index, lambda t: [0.0])

    assert "filter" not in pinecone_index.query.call_args.kwargs

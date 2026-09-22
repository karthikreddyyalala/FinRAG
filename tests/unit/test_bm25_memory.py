"""TDD: the BM25 index must build within a modest memory budget.

818 MB of cached chunk JSON expands to several GB as Python objects, and
pickling the whole structure to a bytes blob allocates it a second time. On
an 8 GB machine that thrashes swap and never finishes -- this step died twice
with no output before the cause was found.
"""
import pickle
from unittest.mock import MagicMock

from pipeline.sync_pinecone import BM25_CHUNK_FIELDS, build_and_store_bm25_index


def _chunk(i):
    """A chunk shaped like chunker.chunk_filing output, including bulk fields."""
    return {
        "chunk_id": f"id-{i}",
        "text": f"revenue grew twelve percent segment {i}",
        "ticker": "MMM",
        "filing_type": "10-K",
        "period": "2019-02-07",
        "page_number": None,
        "chunk_type": "table",
        "section": "table",
        # The bulk: a table's rows are already serialised into `text`, so
        # carrying them again roughly doubles the pickle for table chunks.
        "table_headers": [f"col{j}" for j in range(12)],
        "table_rows": [[f"cell-{i}-{j}-{k}" for k in range(12)] for j in range(40)],
    }


def test_pickle_excludes_bulk_fields_unused_downstream():
    """Only the fields retrieval actually reads should reach S3."""
    s3 = MagicMock()
    build_and_store_bm25_index(s3, "bucket", "bm25/index.pkl", [_chunk(i) for i in range(5)])

    assert s3.upload_fileobj.called or s3.put_object.called, "nothing uploaded"
    if s3.put_object.called:
        payload = pickle.loads(s3.put_object.call_args.kwargs["Body"])
    else:
        fileobj = s3.upload_fileobj.call_args[0][0]
        fileobj.seek(0)
        payload = pickle.loads(fileobj.read())

    stored = payload["chunks"][0]
    assert set(stored) <= set(BM25_CHUNK_FIELDS), f"unexpected fields stored: {set(stored)}"
    assert "table_rows" not in stored, "bulk table_rows was stored"
    assert stored["text"], "text must survive -- rerank and generation need it"
    assert stored["chunk_id"] == "id-0", "chunk_id must survive for dedup against Pinecone"


def test_pickle_is_streamed_not_built_in_memory():
    """A 164k-chunk corpus must not be serialised into a bytes blob first."""
    s3 = MagicMock()
    build_and_store_bm25_index(s3, "bucket", "bm25/index.pkl", [_chunk(i) for i in range(3)])

    assert s3.upload_fileobj.called, (
        "expected a streamed upload (upload_fileobj); put_object(Body=pickle.dumps(...)) "
        "allocates the entire payload in memory"
    )


def test_slimming_preserves_bm25_search_results():
    """Slimming must not change which chunks BM25 returns."""
    from pipeline.sync_pinecone import load_bm25_index
    from server.retrieval.hybrid_retriever import bm25_search

    chunks = [_chunk(i) for i in range(5)]
    chunks[3]["text"] = "unique marker phrase xyzzy"

    s3 = MagicMock()
    build_and_store_bm25_index(s3, "bucket", "bm25/index.pkl", chunks)
    fileobj = s3.upload_fileobj.call_args[0][0]
    fileobj.seek(0)
    blob = fileobj.read()

    get = MagicMock()
    get.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=blob))}
    bm25, stored_chunks = load_bm25_index(get, "bucket", "bm25/index.pkl")

    hits = bm25_search(bm25, stored_chunks, "unique marker phrase xyzzy", top_k=1)
    assert hits[0]["chunk_id"] == "id-3", f"wrong chunk ranked first: {hits[0]['chunk_id']}"

import io
import json
import pickle
from unittest.mock import MagicMock

from pipeline.sync_pinecone import (
    build_and_store_bm25_index,
    chunk_to_pinecone_vector,
    embed_text,
    load_bm25_index,
    sync_chunks_to_pinecone,
)


def _fake_bedrock_client(embedding: list[float]) -> MagicMock:
    client = MagicMock()
    # Fresh BytesIO per call -- a shared stream would be exhausted after the
    # first .read(), unlike a real boto3 streaming body returned per-call.
    client.invoke_model.side_effect = lambda **_kwargs: {
        "body": io.BytesIO(json.dumps({"embedding": embedding}).encode())
    }
    return client


def test_embed_text_calls_titan_and_returns_vector():
    client = _fake_bedrock_client([0.1, 0.2, 0.3])

    vector = embed_text(client, "Nvidia data center revenue grew.")

    assert vector == [0.1, 0.2, 0.3]
    call_kwargs = client.invoke_model.call_args.kwargs
    assert call_kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
    assert "Nvidia data center revenue" in call_kwargs["body"]


def test_chunk_to_pinecone_vector_excludes_bulky_fields():
    chunk = {
        "chunk_id": "abc-123",
        "text": "Data Center | 9000",
        "chunk_type": "table",
        "table_rows": [["Data Center", "9000"]],
        "ticker": "NVDA",
        "page_number": None,
    }

    record = chunk_to_pinecone_vector(chunk, [0.1, 0.2])

    assert record["id"] == "abc-123"
    assert record["values"] == [0.1, 0.2]
    assert "table_rows" not in record["metadata"]
    assert "page_number" not in record["metadata"]  # None values dropped
    assert record["metadata"]["ticker"] == "NVDA"


def test_sync_chunks_to_pinecone_upserts_all_vectors_in_batches():
    client = _fake_bedrock_client([0.1, 0.2])
    index = MagicMock()
    chunks = [
        {"chunk_id": f"id-{i}", "text": f"chunk {i}", "chunk_type": "child", "ticker": "NVDA"}
        for i in range(3)
    ]

    total = sync_chunks_to_pinecone(client, index, chunks, batch_size=2)

    assert total == 3
    assert index.upsert.call_count == 2  # batch of 2, then batch of 1


def test_build_and_store_bm25_index_pickles_index_and_chunks():
    s3 = MagicMock()
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew significantly"},
        {"chunk_id": "c2", "text": "Apple iPhone revenue declined slightly"},
        {"chunk_id": "c3", "text": "Tesla gross margin expanded in recent quarters"},
        {"chunk_id": "c4", "text": "Microsoft cloud revenue accelerating quarter over quarter"},
    ]

    build_and_store_bm25_index(s3, "finrag-processed-filings", "bm25/index.pkl", chunks)

    s3.put_object.assert_called_once()
    call_kwargs = s3.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "finrag-processed-filings"
    assert call_kwargs["Key"] == "bm25/index.pkl"
    payload = pickle.loads(call_kwargs["Body"])
    assert payload["chunks"] == chunks
    # Verify BM25 is callable and returns scores for all documents
    scores = payload["bm25"].get_scores(["nvidia", "revenue"])
    assert len(scores) == len(chunks)
    assert scores[0] > scores[1]  # Nvidia doc should score higher for nvidia+revenue


def test_load_bm25_index_round_trips_through_pickle():
    s3 = MagicMock()
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew significantly"},
        {"chunk_id": "c2", "text": "Apple iPhone market share declined"},
        {"chunk_id": "c3", "text": "Tesla gross margin expanded in recent quarters"},
    ]
    build_and_store_bm25_index(s3, "bucket", "key", chunks)
    stored_body = s3.put_object.call_args.kwargs["Body"]
    s3.get_object.return_value = {"Body": MagicMock(read=lambda: stored_body)}

    bm25, loaded_chunks = load_bm25_index(s3, "bucket", "key")

    assert loaded_chunks == chunks
    # Verify BM25 is callable and returns scores
    scores = bm25.get_scores(["nvidia"])
    assert len(scores) == len(chunks)
    assert scores[0] > scores[1]  # Nvidia doc should score higher

import io
import json
from unittest.mock import MagicMock

from pipeline.sync_pinecone import chunk_to_pinecone_vector, embed_text, sync_chunks_to_pinecone


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

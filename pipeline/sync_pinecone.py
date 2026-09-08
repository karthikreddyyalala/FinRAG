"""Embeds chunks with Bedrock Titan V2 and upserts them into Pinecone.

Uses the `pinecone` package (not the deprecated `pinecone-client`).
"""
from __future__ import annotations

import json
from typing import Any

from pinecone import Pinecone

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


def embed_text(bedrock_client: Any, text: str) -> list[float]:
    """Embed one chunk of text using Bedrock Titan Text Embeddings V2.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        text: Chunk text to embed.

    Returns:
        Embedding vector as a list of floats.
    """
    response = bedrock_client.invoke_model(
        modelId=TITAN_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIMENSIONS}),
    )
    payload = json.loads(response["body"].read())
    return payload["embedding"]


def chunk_to_pinecone_vector(chunk: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    """Build a Pinecone upsert record from a chunk and its embedding.

    Args:
        chunk: A chunk dict produced by chunker.py.
        embedding: The embedding vector from embed_text().

    Returns:
        {"id": ..., "values": ..., "metadata": ...} ready for Pinecone upsert.
        Bulky/non-scalar fields and None values are dropped -- Pinecone
        metadata must be JSON-scalar-ish and rejects null values.
    """
    metadata = {
        k: v
        for k, v in chunk.items()
        if k not in {"chunk_id", "table_rows"} and v is not None
    }
    return {"id": chunk["chunk_id"], "values": embedding, "metadata": metadata}


def sync_chunks_to_pinecone(
    bedrock_client: Any,
    pinecone_index: Any,
    chunks: list[dict[str, Any]],
    batch_size: int = 100,
) -> int:
    """Embed and upsert a list of chunks into a Pinecone index.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle (Pinecone().Index(name)).
        chunks: Chunks produced by chunker.chunk_filing().
        batch_size: Max vectors per Pinecone upsert call.

    Returns:
        Total number of vectors upserted.
    """
    vectors = [
        chunk_to_pinecone_vector(chunk, embed_text(bedrock_client, chunk["text"]))
        for chunk in chunks
    ]

    total = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        pinecone_index.upsert(vectors=batch)
        total += len(batch)
    return total


def get_pinecone_index(api_key: str, index_name: str) -> Any:
    """Return a handle to a named Pinecone index.

    Args:
        api_key: Pinecone API key (read from env by the caller).
        index_name: Name of the target Pinecone index.

    Returns:
        A Pinecone Index object.
    """
    pc = Pinecone(api_key=api_key)
    return pc.Index(index_name)

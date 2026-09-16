"""Embeds chunks with Bedrock Titan V2 and upserts them into Pinecone.

Uses the `pinecone` package (not the deprecated `pinecone-client`).
"""
from __future__ import annotations

import json
import pickle
import time
from typing import Any

from pinecone import Pinecone
from rank_bm25 import BM25Okapi

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1536
OPENAI_EMBED_MODEL = "text-embedding-3-small"  # 1536 dims, fast, $0.02/1M tokens

_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        import os

        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


def embed_text_openai(text: str) -> list[float]:
    """Embed a single text via OpenAI — fast, no local compute needed."""
    client = _get_openai_client()
    return client.embeddings.create(input=[text], model=OPENAI_EMBED_MODEL).data[0].embedding


def embed_texts_openai(texts: list[str]) -> list[list[float]]:
    """Batch embed up to 2048 texts in one OpenAI API call."""
    client = _get_openai_client()
    # 8191 token limit; use 6000 chars (~1500 tokens) to stay safe on dense numeric content
    safe = [t[:6000] for t in texts]
    resp = client.embeddings.create(input=safe, model=OPENAI_EMBED_MODEL)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def embed_text(bedrock_client: Any, text: str, max_retries: int = 8) -> list[float]:
    """Embed one chunk of text using Bedrock Titan Text Embeddings V2.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        text: Chunk text to embed.
        max_retries: Retries with exponential backoff on ThrottlingException.

    Returns:
        Embedding vector as a list of floats.
    """
    delay = 10.0  # start at 10s; Bedrock free-tier is ~10 req/min
    for attempt in range(max_retries):
        try:
            response = bedrock_client.invoke_model(
                modelId=TITAN_MODEL_ID,
                body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIMENSIONS}),
            )
            return json.loads(response["body"].read())["embedding"]
        except Exception as exc:
            throttled = "ThrottlingException" in type(exc).__name__ or "Throttling" in str(exc)
            if not throttled:
                raise
            if attempt == max_retries - 1:
                raise
            print(f"    throttled, waiting {delay:.0f}s ...")
            time.sleep(delay)
            delay = min(delay * 2, 120)  # cap at 2 min
    raise RuntimeError("embed_text: exhausted retries")


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
        k: (v[:1000] if isinstance(v, str) else v)
        for k, v in chunk.items()
        if k not in {"chunk_id", "table_rows"} and v is not None
    }
    return {"id": chunk["chunk_id"], "values": embedding, "metadata": metadata}


def sync_chunks_to_pinecone(
    bedrock_client: Any,
    pinecone_index: Any,
    chunks: list[dict[str, Any]],
    batch_size: int = 100,
    embed_fn=None,
    embed_batch_fn=None,
) -> int:
    """Embed and upsert a list of chunks into a Pinecone index.

    Args:
        bedrock_client: A boto3 bedrock-runtime client (used when embed_fn is None).
        pinecone_index: A Pinecone Index handle (Pinecone().Index(name)).
        chunks: Chunks produced by chunker.chunk_filing().
        batch_size: Max vectors per Pinecone upsert call.
        embed_fn: Optional callable(text)->vector. Defaults to Bedrock Titan.
        embed_batch_fn: Optional callable(list[text])->list[vector]. When given,
                  takes precedence over embed_fn -- one request per batch
                  instead of one per chunk. Pass embed_texts_openai for
                  corpus-scale ingestion.

    Returns:
        Total number of vectors upserted.
    """
    texts = [c["text"] for c in chunks]
    if embed_batch_fn is not None:
        print(f"  batch-embedding {len(chunks)} chunks ...", flush=True)
        embeddings = embed_batch_fn(texts)
    else:
        if embed_fn is None:
            embed_fn = lambda text: embed_text(bedrock_client, text)  # noqa: E731
        embeddings = [embed_fn(t) for t in texts]

    vectors = [chunk_to_pinecone_vector(c, e) for c, e in zip(chunks, embeddings)]
    print(f"  embedded {len(vectors)} chunks, upserting to Pinecone ...")

    total = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        pinecone_index.upsert(vectors=batch)
        total += len(batch)
    return total


def get_embed_fn(bedrock_client: Any = None):
    """Return a callable(text) -> embedding vector. Uses OpenAI text-embedding-3-small."""
    return embed_text_openai


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


def build_and_store_bm25_index(
    s3_client: Any, bucket: str, key: str, chunks: list[dict[str, Any]]
) -> None:
    """Build a BM25 keyword index from chunk text and pickle it to S3.

    BM25Okapi has no persistence of its own, so the index and its source
    chunks are pickled together -- a BM25 hit resolves straight to full
    chunk metadata without a second lookup at query time.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Destination bucket (finrag-processed-filings).
        key: S3 key to store the pickled index at.
        chunks: All chunks across the corpus, from chunker.chunk_filing().
    """
    # ponytail: basic whitespace tokenization (no stemming/stopwords);
    # upgrade to spacy/nltk in Week 3 if query quality metrics warrant
    tokenized = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    # pickle is safe here: only ever written by this project's own ingestion
    # pipeline and read back by its own query-time code -- no untrusted data path
    payload = pickle.dumps({"bm25": bm25, "chunks": chunks})
    s3_client.put_object(Bucket=bucket, Key=key, Body=payload)


def load_bm25_index(
    s3_client: Any, bucket: str, key: str
) -> tuple[BM25Okapi, list[dict[str, Any]]]:
    """Load a pickled BM25 index and its source chunks from S3.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Bucket the index was stored in.
        key: S3 key the index was stored at.

    Returns:
        (bm25_index, chunks) -- chunks[i] is the source chunk for the i-th
        entry in bm25_index's internal corpus, in the same order.
    """
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    payload = pickle.loads(obj["Body"].read())
    return payload["bm25"], payload["chunks"]

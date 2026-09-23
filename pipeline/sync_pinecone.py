"""Embeds chunks with Bedrock Titan V2 and upserts them into Pinecone.

Uses the `pinecone` package (not the deprecated `pinecone-client`).
"""
from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pinecone import Pinecone

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1536
OPENAI_EMBED_MODEL = "text-embedding-3-small"  # 1536 dims, fast, $0.02/1M tokens

# OpenAI embeddings request limits. The API's ceiling is 300k tokens per
# request, but its server-side accounting runs well above what tiktoken
# reports for the same payload -- a batch measured at 249,174 tokens with
# cl100k_base (the encoding the model actually uses) was rejected as 308,368,
# a factor of 1.24. The budget therefore carries ~2x headroom rather than
# trusting the local count. Extra requests are cheap; a rejected batch
# silently drops a whole filing from the corpus.
MAX_TOKENS_PER_REQUEST = 150_000
MAX_ITEMS_PER_REQUEST = 2048
MAX_CHARS_PER_TEXT = 6000

# The only chunk fields read downstream (rerank, generation, citations, and
# chunk_id for dedup against Pinecone). Everything else -- table_rows in
# particular -- is dead weight in the BM25 payload.
BM25_CHUNK_FIELDS = ("chunk_id", "text", "ticker", "filing_type", "period", "page_number")

# Observed ratio of OpenAI's server-side count to tiktoken's. Used by tests
# to assert the budget keeps real requests under the API cap.
OBSERVED_SERVER_TOKEN_RATIO = 1.24

_openai_client = None
_encoder = None


def _count_tokens(text: str) -> int:
    """Exact token count via tiktoken, with a pessimistic fallback.

    Counted, not estimated: a chars/4 heuristic assumes 0.25 tokens/char, but
    digit-dense financial tables measure up to 0.63 -- so a batch "estimated"
    at 250k tokens really carried 613k and the API rejected the whole request.
    tiktoken ships with the openai SDK, so this costs no new dependency.
    """
    global _encoder
    if _encoder is None:
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _encoder = False  # fall back permanently rather than retry per call
    if _encoder is False:
        return len(text) // 2 + 1  # assume the worst-observed density
    return len(_encoder.encode(text))


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
    """Embed texts via OpenAI, splitting into requests that fit the API limits.

    Splitting is required, not an optimization: a single large 10-K produces
    enough chunks to exceed the 300k-token request cap, and OpenAI rejects
    the entire call with a 400. Callers ingest filing-by-filing and swallow
    exceptions, so an unsplit batch shows up as a company silently missing
    from the corpus rather than as an error.

    Returns one vector per input, in input order.
    """
    client = _get_openai_client()
    # Per-input cap is 8191 tokens; 6000 chars (~1500 tokens) stays clear of
    # it even for dense numeric tables, which tokenize far worse than prose.
    safe = [t[:MAX_CHARS_PER_TEXT] for t in texts]

    vectors: list[list[float]] = []
    batch: list[str] = []
    batch_tokens = 0

    def flush() -> None:
        nonlocal batch, batch_tokens
        if not batch:
            return
        resp = client.embeddings.create(input=batch, model=OPENAI_EMBED_MODEL)
        vectors.extend(item.embedding for item in sorted(resp.data, key=lambda x: x.index))
        batch = []
        batch_tokens = 0

    for text in safe:
        est = _count_tokens(text)
        over_tokens = batch and batch_tokens + est > MAX_TOKENS_PER_REQUEST
        over_items = len(batch) >= MAX_ITEMS_PER_REQUEST
        if over_tokens or over_items:
            flush()
        batch.append(text)
        batch_tokens += est

    flush()
    return vectors


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


_FTS_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was were what when where which who will with".split()
)


def _fts_match_expression(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression: quoted terms, OR-ed.

    Raw query text must never reach MATCH as FTS5 syntax. Quotes, NEAR(),
    column filters ("text:"), leading "-", and bare AND/OR either raise a
    syntax error or silently change what is searched. Each term is reduced to
    word characters and double-quoted, so it can only ever be a literal term.
    OR-ing them matches BM25's any-term semantics; bm25() does the ranking.
    """
    terms = [t for t in re.findall(r"\w+", query.lower()) if t not in _FTS_STOPWORDS]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))


class KeywordIndex:
    """BM25 keyword search over chunks, backed by an on-disk SQLite FTS5 table.

    Replaces the in-memory rank-bm25 pickle, which stopped scaling at 164k
    chunks: building it peaked at 7.5 GB, loading took 212 s, and its
    whitespace tokeniser left punctuation attached ("property," never matched
    "property"). FTS5 still ranks with BM25 -- its built-in bm25() -- but reads
    pages from disk on demand and tokenises and stems properly.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Open an existing index read-only.

        Args:
            db_path: Path to a file written by build_keyword_index().
        """
        # check_same_thread=False: hybrid_search queries from a worker thread.
        # Safe here -- the connection is read-only and SQLite is serialised.
        self._conn = sqlite3.connect(
            f"file:{Path(db_path).resolve()}?mode=ro", uri=True, check_same_thread=False
        )

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Return up to top_k chunks, best BM25 match first.

        Args:
            query: Free-text query; any FTS5 syntax in it is neutralised.
            top_k: Maximum number of chunks to return.

        Returns:
            Chunk dicts with exactly BM25_CHUNK_FIELDS.
        """
        expression = _fts_match_expression(query)
        if not expression:
            return []
        rows = self._conn.execute(
            f"SELECT {', '.join(BM25_CHUNK_FIELDS)} FROM chunks "
            "WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (expression, top_k),
        ).fetchall()
        return [dict(zip(BM25_CHUNK_FIELDS, row)) for row in rows]


def build_keyword_index(db_path: str | Path, chunks: Iterable[dict[str, Any]]) -> int:
    """Write chunks to a new SQLite FTS5 index, streaming, in bounded memory.

    Args:
        db_path: Where to write the index. Overwritten if it exists.
        chunks: Chunks from chunker.chunk_filing() -- any iterable, so a caller
            can stream from disk instead of materialising the whole corpus.

    Returns:
        Number of chunks written.
    """
    path = Path(db_path)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    unindexed = ", ".join(f"{f} UNINDEXED" for f in BM25_CHUNK_FIELDS if f != "text")
    # porter: "purchases" and "purchase" share a stem, so inflections match.
    conn.execute(
        f"CREATE VIRTUAL TABLE chunks USING fts5(text, {unindexed}, "
        "tokenize='porter unicode61')"
    )
    columns = ("text", *(f for f in BM25_CHUNK_FIELDS if f != "text"))
    insert = f"INSERT INTO chunks ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})"

    count = 0
    batch: list[tuple[Any, ...]] = []
    for chunk in chunks:
        batch.append(tuple(chunk.get(c) for c in columns))
        if len(batch) >= 5000:
            conn.executemany(insert, batch)
            count += len(batch)
            batch = []
    if batch:
        conn.executemany(insert, batch)
        count += len(batch)
    conn.commit()
    conn.execute("INSERT INTO chunks(chunks) VALUES ('optimize')")  # merge b-trees
    conn.commit()
    conn.close()
    return count


def build_and_store_keyword_index(
    s3_client: Any, bucket: str, key: str, chunks: Iterable[dict[str, Any]]
) -> int:
    """Build the keyword index to a temp file and upload it to S3.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Destination bucket (finrag-processed-filings).
        key: S3 key for the index file.
        chunks: All chunks across the corpus.

    Returns:
        Number of chunks indexed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keyword.sqlite"
        count = build_keyword_index(path, chunks)
        s3_client.upload_file(str(path), bucket, key)  # multipart for large files
    return count


def load_keyword_index(
    s3_client: Any,
    bucket: str,
    key: str,
    local_path: str | Path,
    max_retries: int = 5,
    retry_delay: float = 5.0,
) -> KeywordIndex:
    """Download the keyword index once and open it.

    A warm Lambda reuses the file already in /tmp rather than downloading it
    again. The download lands on a temp name and is renamed only once
    complete: a partial file left at the final path would otherwise pass the
    exists-check and be reused on every later request. Only ReadTimeoutError
    is retried -- a missing key or bad permissions fails immediately.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Bucket holding the index.
        key: S3 key of the index file.
        local_path: Where to keep the downloaded file.
        max_retries: Download attempts before giving up.
        retry_delay: Initial backoff in seconds, doubled per retry.

    Returns:
        An open KeywordIndex.
    """
    import botocore.exceptions

    path = Path(local_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        delay = retry_delay
        for attempt in range(max_retries):
            try:
                s3_client.download_file(bucket, key, str(partial))
                partial.replace(path)
                break
            except botocore.exceptions.ReadTimeoutError:
                partial.unlink(missing_ok=True)
                if attempt == max_retries - 1:
                    raise
                print(f"    S3 read timeout, retrying in {delay:.0f}s ...", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
    return KeywordIndex(path)

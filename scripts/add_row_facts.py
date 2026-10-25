"""Add one searchable fact per table row of each annual report.

Reads each ticker's cached table chunks, makes facts (pipeline/row_facts.py),
embeds and upserts them to Pinecone, and appends them to the chunk cache (local
and S3) so the weekly keyword-index rebuild includes them. Fact ids start with
"fact_", so the whole batch can be listed and deleted from Pinecone by prefix.

Only 10-K tables: quarterly tables mix three-month and nine-month columns, which
the row parser cannot align to years safely.

Run: PYTHONPATH=. python3 scripts/add_row_facts.py TICKER [TICKER ...] [--local-index PATH]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from pipeline.row_facts import table_row_facts
from pipeline.sync_pinecone import (
    build_keyword_index,
    embed_texts_openai,
    get_pinecone_index,
    sync_chunks_to_pinecone,
)
from scripts.bootstrap_corpus import (
    CHUNK_CACHE,
    PROCESSED_BUCKET,
    _iter_cached_chunks,
)
from scripts.weekly_refresh import CHUNK_CACHE_S3_PREFIX


def new_facts(cached: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Facts for this ticker's 10-K tables that the cache does not hold yet."""
    have = {c["chunk_id"] for c in cached if c.get("chunk_type") == "fact"}
    facts: dict[str, dict[str, Any]] = {}
    for c in cached:
        if c.get("chunk_type") != "table" or c.get("filing_type") != "10-K":
            continue
        for fact in table_row_facts(c["text"], c):
            if fact["chunk_id"] not in have:
                facts[fact["chunk_id"]] = fact
    return list(facts.values())


def main() -> None:
    args = sys.argv[1:]
    local_index = None
    if "--local-index" in args:
        i = args.index("--local-index")
        local_index = Path(args[i + 1])
        del args[i : i + 2]
    tickers = args
    if not tickers:
        print(__doc__)
        sys.exit(1)

    import boto3

    s3 = boto3.client("s3")
    index = get_pinecone_index(api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings")
    for ticker in tickers:
        cache_file = CHUNK_CACHE / f"{ticker}.json"
        cached = json.loads(cache_file.read_text())
        facts = new_facts(cached)
        print(f"{ticker}: {len(facts)} new facts", flush=True)
        if not facts:
            continue
        sync_chunks_to_pinecone(None, index, facts, embed_batch_fn=embed_texts_openai)
        cache_file.write_text(json.dumps(cached + facts))
        s3.upload_file(str(cache_file), PROCESSED_BUCKET, f"{CHUNK_CACHE_S3_PREFIX}{ticker}.json")

    if local_index:
        n = build_keyword_index(local_index, _iter_cached_chunks(CHUNK_CACHE))
        print(f"Local keyword index (NOT published) built at {local_index}: {n} chunks")


if __name__ == "__main__":
    main()

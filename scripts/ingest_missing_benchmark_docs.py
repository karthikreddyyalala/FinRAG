"""Ingest only the FinanceBench source filings the corpus is missing.

The weekly refresh and the bootstrap read EDGAR's "recent filings" list, which
stops short of 2015-2017 for big filers, so a handful of benchmark documents
were never ingested. This finds them from the official document labels, pulls
them from EDGAR's older submission pages, embeds and upserts them, merges them
into the chunk cache (S3 is the source of truth), and republishes the keyword
index.

Run: PYTHONPATH=. python3 scripts/ingest_missing_benchmark_docs.py [--dry-run]
Costs: OpenAI embeddings and Pinecone writes for roughly 17 filings.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import boto3

from evals.failure_breakdown import NAME_TO_TICKER, missing_docs, parse_doc_name
from pipeline.chunker import chunk_filing
from pipeline.edgar_client import (
    FilingMetadata,
    _get_with_retry,
    download_filing,
    get_cik_for_ticker,
    store_filing,
)
from pipeline.edgar_history import all_submission_rows, select_filings
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import (
    build_and_store_keyword_index,
    embed_texts_openai,
    get_pinecone_index,
    sync_chunks_to_pinecone,
)
from scripts.bootstrap_corpus import (
    CHUNK_CACHE,
    KEYWORD_INDEX_KEY,
    PROCESSED_BUCKET,
    RAW_BUCKET,
    TARGET_TICKERS,
    _iter_cached_chunks,
)
from scripts.weekly_refresh import CHUNK_CACHE_S3_PREFIX, _sync_chunk_cache_from_s3

DOCS = Path(__file__).resolve().parent.parent / "evals" / "eval_data" / "financebench_docs.json"


def plan_by_ticker(names: list[str], rows: list[dict]) -> dict[str, list[tuple]]:
    """Group missing document names into {ticker: [(year, quarter, form), ...]}."""
    company = {r["doc_name"]: r["company"] for r in rows}
    plan: dict[str, list[tuple]] = {}
    for name in names:
        parsed = parse_doc_name(name)
        if parsed is None:
            continue
        ticker = NAME_TO_TICKER.get(company[name], company[name])
        plan.setdefault(ticker, []).append(parsed)
    return plan


def merge_chunks(existing: list[dict], new: list[dict]) -> list[dict]:
    """Append new chunks whose chunk_id is not already present."""
    seen = {c["chunk_id"] for c in existing}
    return existing + [c for c in new if c["chunk_id"] not in seen]


def _get_json(url: str) -> dict[str, Any]:
    return _get_with_retry(url, timeout=15).json()


def ingest_ticker(
    s3: Any, bedrock: Any, index: Any, ticker: str, wanted: list[tuple]
) -> list[dict]:
    """Download, chunk, embed and upsert one ticker's wanted filings (all or nothing)."""
    cik = get_cik_for_ticker(ticker)
    picked = select_filings(wanted, all_submission_rows(cik, _get_json))
    if len(picked) != len(wanted):
        raise RuntimeError(f"{ticker}: found {len(picked)} of {len(wanted)} wanted filings")
    chunks: list[dict] = []
    for row in picked:
        filing = FilingMetadata(
            ticker=ticker, cik=cik, form_type=row["form"], filing_date=row["filingDate"],
            accession_number=row["accessionNumber"], primary_document=row["primaryDocument"],
        )
        html = download_filing(filing).decode("utf-8", errors="ignore")
        store_filing(s3, RAW_BUCKET, filing, html.encode("utf-8"))
        meta = {"ticker": ticker, "filing_type": row["form"], "period": row["filingDate"]}
        new = chunk_filing(process_filing(html, meta))
        sync_chunks_to_pinecone(bedrock, index, new, embed_batch_fn=embed_texts_openai)
        print(f"  {ticker} {row['form']} {row['filingDate']}: {len(new)} chunks", flush=True)
        chunks.extend(new)
    return chunks


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    rows = json.loads(DOCS.read_text())
    s3 = boto3.client("s3")
    bedrock = boto3.client("bedrock-runtime")

    print("Syncing chunk cache from S3 (source of truth) ...", flush=True)
    _sync_chunk_cache_from_s3(s3, PROCESSED_BUCKET, CHUNK_CACHE)

    plan = plan_by_ticker(missing_docs(rows, {}), rows)
    print(f"Missing filings: {sum(len(v) for v in plan.values())} across {sorted(plan)}")
    if dry_run:
        for ticker, wanted in sorted(plan.items()):
            print(f"  {ticker}: {wanted}")
        return

    index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    changed: list[str] = []
    failed: list[str] = []
    for ticker, wanted in sorted(plan.items()):
        print(f"{ticker}: ingesting {len(wanted)} filing(s) ...", flush=True)
        try:
            new = ingest_ticker(s3, bedrock, index, ticker, wanted)
        except Exception as e:
            failed.append(ticker)
            print(f"{ticker}: FAILED - {e}", flush=True)
            continue
        cache_file = CHUNK_CACHE / f"{ticker}.json"
        existing = json.loads(cache_file.read_text()) if cache_file.exists() else []
        cache_file.write_text(json.dumps(merge_chunks(existing, new)))
        s3.upload_file(str(cache_file), PROCESSED_BUCKET, f"{CHUNK_CACHE_S3_PREFIX}{ticker}.json")
        changed.append(ticker)

    if failed:
        print(f"\nFAILED: {sorted(failed)}")
    if not changed:
        print("Nothing ingested; keyword index unchanged.")
        sys.exit(1 if failed else 0)

    # Same publish guard as bootstrap/weekly refresh: never replace the index in S3
    # with one built from partial coverage.
    covered = {
        t for t in TARGET_TICKERS
        if (CHUNK_CACHE / f"{t}.json").exists()
        and json.loads((CHUNK_CACHE / f"{t}.json").read_text())
    }
    uncovered = sorted(set(TARGET_TICKERS) - covered - {"SPOT", "PYPL"})
    if uncovered:
        print(f"Skipping keyword index publish: uncovered tickers {uncovered}")
        sys.exit(1)
    count = build_and_store_keyword_index(
        s3, PROCESSED_BUCKET, KEYWORD_INDEX_KEY, _iter_cached_chunks(CHUNK_CACHE)
    )
    print(f"Keyword index rebuilt: {count} chunks across {len(covered)} companies")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

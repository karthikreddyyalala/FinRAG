"""EventBridge weekly cron target: ingest only what EDGAR added since last run.

bootstrap_corpus.py's per-ticker cache means "ingested once, skip forever" --
right for a one-time seed, wrong for a recurring refresh, since re-running it
against an already-seeded corpus would skip every ticker without ever
checking EDGAR again. Re-ingesting everything on a schedule instead would
re-embed and re-upsert 2,000+ unchanged filings every week -- real OpenAI
spend, and the same Pinecone free-tier write cap that already cost this
project a FinanceBench question. This script diffs EDGAR's current filing
list against the cache (by filing_date) and touches only what's new.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from typing import Any

import boto3

from pipeline.chunker import chunk_filing
from pipeline.edgar_client import download_filing, get_cik_for_ticker, list_filings, store_filing
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import (
    build_and_store_keyword_index,
    embed_texts_openai,
    get_pinecone_index,
    sync_chunks_to_pinecone,
)
from scripts.bootstrap_corpus import (
    BENCHMARK_FORM_LIMITS,
    BENCHMARK_TICKERS,
    CHUNK_CACHE,
    KEYWORD_INDEX_KEY,
    KNOWN_UNAVAILABLE,
    PROCESSED_BUCKET,
    RAW_BUCKET,
    TARGET_TICKERS,
    _iter_cached_chunks,
)
from server.ssm_secrets import load_secrets_from_ssm


def refresh_ticker(
    s3_client: Any,
    bedrock_client: Any,
    pinecone_index: Any,
    ticker: str,
    cached_chunks: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """Ingest only filings EDGAR has that aren't already in the cache.

    Args:
        s3_client: A boto3 S3 client.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        ticker: Stock ticker symbol to refresh.
        cached_chunks: This ticker's existing chunks from CHUNK_CACHE.

    Returns:
        (new chunks synced, merged chunk list -- cached_chunks unchanged and
        returned as-is when nothing new was found).

    Raises:
        RuntimeError: A new filing failed partway through. Matches
            bootstrap_ticker's all-or-nothing discipline: returning a
            partial result here would let main() cache a filing as done
            that was never actually ingested, so the next run would never
            retry it.
    """
    seen_dates = {c["period"] for c in cached_chunks}
    cik = get_cik_for_ticker(ticker)
    limits = BENCHMARK_FORM_LIMITS if ticker in BENCHMARK_TICKERS else None
    filings = list_filings(ticker, cik, form_limits=limits)
    new_filings = [f for f in filings if f.filing_date not in seen_dates]

    if not new_filings:
        return 0, cached_chunks

    new_chunks: list[dict[str, Any]] = []
    failures: list[str] = []
    for filing in new_filings:
        try:
            html = download_filing(filing).decode("utf-8", errors="ignore")
            store_filing(s3_client, RAW_BUCKET, filing, html.encode("utf-8"))
            metadata = {
                "ticker": filing.ticker,
                "filing_type": filing.form_type,
                "period": filing.filing_date,
            }
            processed = process_filing(html, metadata)
            chunks = chunk_filing(processed)
            sync_chunks_to_pinecone(
                bedrock_client, pinecone_index, chunks, embed_batch_fn=embed_texts_openai
            )
            new_chunks.extend(chunks)
        except Exception as e:
            print(f"{ticker} {filing.accession_number}: failed - {e}", flush=True)
            failures.append(filing.accession_number)

    if failures:
        raise RuntimeError(
            f"{ticker}: {len(failures)}/{len(new_filings)} new filings failed ({failures})"
        )

    return len(new_chunks), cached_chunks + new_chunks


def main() -> None:
    """Refresh every ticker and rebuild the keyword index only if anything changed."""
    mp.set_start_method("spawn", force=True)

    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )

    any_new = False
    failed: list[str] = []
    for i, ticker in enumerate(TARGET_TICKERS, 1):
        if ticker in KNOWN_UNAVAILABLE:
            print(
                f"[{i}/{len(TARGET_TICKERS)}] {ticker}: skipped -- {KNOWN_UNAVAILABLE[ticker]}",
                flush=True,
            )
            continue

        cache_file = CHUNK_CACHE / f"{ticker}.json"
        cached_chunks = json.loads(cache_file.read_text()) if cache_file.exists() else []
        try:
            new_count, merged = refresh_ticker(
                s3_client, bedrock_client, pinecone_index, ticker, cached_chunks
            )
        except Exception as e:
            failed.append(ticker)
            print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: FAILED - {e}", flush=True)
            continue

        if new_count:
            cache_file.write_text(json.dumps(merged))
            any_new = True
            print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: {new_count} new chunks", flush=True)
        else:
            print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: up to date", flush=True)

    if failed:
        print(f"\nFAILED ({len(failed)}): {sorted(failed)}")
        sys.exit(1)

    if not any_new:
        print("\nNo new filings found across the corpus -- keyword index unchanged.")
        return

    def _has_chunks(cache_file):
        return cache_file.exists() and json.loads(cache_file.read_text())

    covered = {
        t for t in TARGET_TICKERS if _has_chunks(CHUNK_CACHE / f"{t}.json")
    }
    unavailable = sorted(set(TARGET_TICKERS) - covered - set(KNOWN_UNAVAILABLE))
    if unavailable:
        # Same publish guard as bootstrap_corpus.py: never overwrite a
        # complete index in S3 with one built from partial coverage.
        print(f"\nSkipping keyword index publish: uncovered tickers {unavailable}")
        sys.exit(1)

    count = build_and_store_keyword_index(
        s3_client, PROCESSED_BUCKET, KEYWORD_INDEX_KEY, _iter_cached_chunks(CHUNK_CACHE)
    )
    print(f"\nKeyword index rebuilt: {count} chunks across {len(covered)} companies")


def handler(event: Any, context: Any) -> None:
    """EventBridge Lambda entry point: load secrets from SSM, then refresh."""
    load_secrets_from_ssm(
        boto3.client("ssm"), prefix=os.environ.get("FINRAG_SSM_PREFIX", "/finrag")
    )
    main()


if __name__ == "__main__":
    main()

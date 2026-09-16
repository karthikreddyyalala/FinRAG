"""One-time bootstrap: ingest the initial 50-company corpus end to end.

Runs edgar_client -> html_processor -> chunker -> sync_pinecone for each
ticker in TARGET_TICKERS, then builds one corpus-wide BM25 index from all
chunks and stores it to S3. Run once locally to seed the corpus before the
weekly refresh cron (Week 4+) takes over.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import Any

import boto3

from pipeline.chunker import chunk_filing
from pipeline.edgar_client import download_filing, get_cik_for_ticker, list_filings, store_filing
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import (
    build_and_store_bm25_index,
    embed_texts_openai,
    get_pinecone_index,
    sync_chunks_to_pinecone,
)

TARGET_TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",       # Tech
    "TSLA", "F", "GM", "RIVN", "LCID",             # EV/Auto
    "JPM", "BAC", "GS", "MS", "V",                 # Finance
    "JNJ", "PFE", "UNH", "ABBV", "MRK",            # Healthcare
    "XOM", "CVX", "COP", "SLB", "OXY",             # Energy
    "WMT", "COST", "HD", "TGT", "LOW",             # Consumer Retail
    "BA", "CAT", "GE", "HON", "UPS",               # Industrials
    "T", "VZ", "TMUS", "CMCSA", "CHTR",            # Telecom
    "DIS", "NFLX", "WBD", "PARA", "SPOT",          # Media
    "AMD", "INTC", "QCOM", "TXN", "AVGO",          # Semiconductors
    # FinanceBench coverage. Without these, 101 of the benchmark's 150
    # questions ask about companies absent from the corpus -- retrieval
    # returns a confidently wrong company rather than nothing, so the gap
    # shows up as bad scores rather than as an obvious error.
    "MMM", "PEP", "AMCR", "BBY", "AXP",
    "MGM", "ULTA", "ADBE", "GLW", "CVS",
    "GIS", "NKE", "AES", "AMZN", "AWK",
    "SQ", "KO", "LMT", "ATVI", "FL",
    "KHC", "PYPL",
]

RAW_BUCKET = "finrag-raw-filings"
PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"
CHUNK_CACHE = Path(__file__).parent.parent / "evals" / "results" / "chunk_cache"

# Companies FinanceBench asks about. They get deep history; the rest of the
# corpus exists for breadth and keeps the cheap default depth.
BENCHMARK_TICKERS = {
    "MMM", "ATVI", "ADBE", "AES", "AMZN", "AMCR", "AMD", "AXP", "AWK", "BBY",
    "SQ", "BA", "KO", "GLW", "COST", "CVS", "FL", "GIS", "JNJ", "JPM", "KHC",
    "LMT", "MGM", "MSFT", "NFLX", "NKE", "PYPL", "PEP", "PFE", "ULTA", "VZ",
    "WMT",
}

# A 10-K filed in early 2019 reports FY2018, so 8 annual reports reach back
# roughly a decade -- the span FinanceBench actually asks about (2015-2024).
# Ingesting only the last 2 left the corpus holding 2025-2026 filings, which
# could not answer 147 of the 150 questions.
BENCHMARK_FORM_LIMITS = {"10-K": 8, "10-Q": 12, "8-K": 8}


def bootstrap_ticker(
    s3_client: Any, bedrock_client: Any, pinecone_index: Any, ticker: str
) -> tuple[int, list[dict[str, Any]]]:
    """Ingest, process, chunk, and sync one ticker's filings end to end.

    Args:
        s3_client: A boto3 S3 client.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        ticker: Stock ticker symbol to bootstrap.

    Returns:
        (total chunks synced, all chunks processed) -- chunks are returned
        so main() can accumulate them corpus-wide for the BM25 index built
        once after every ticker is done.
    """
    cik = get_cik_for_ticker(ticker)
    limits = BENCHMARK_FORM_LIMITS if ticker in BENCHMARK_TICKERS else None
    filings = list_filings(ticker, cik, form_limits=limits)

    total_chunks = 0
    all_chunks: list[dict[str, Any]] = []
    failures: list[str] = []
    for filing in filings:
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
            total_chunks += sync_chunks_to_pinecone(
                bedrock_client, pinecone_index, chunks, embed_batch_fn=embed_texts_openai
            )
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"{ticker} {filing.accession_number}: failed - {e}", flush=True)
            failures.append(filing.accession_number)
            continue

    if failures:
        # Raise rather than return partial data: main() caches whatever comes
        # back and treats a cached ticker as done, so a silent partial result
        # is indistinguishable from a complete one on the next run.
        raise RuntimeError(
            f"{ticker}: {len(failures)}/{len(filings)} filings failed ({failures})"
        )

    return total_chunks, all_chunks


def main() -> None:
    """Bootstrap the full corpus and build one BM25 index over every chunk.

    Resumable: each ticker's chunks are written to CHUNK_CACHE as it
    completes, so a network drop mid-run costs one ticker, not the whole
    corpus. Delete a ticker's cache file to force it to re-ingest.
    """
    # "spawn" avoids the fork-safety crash macOS raises when boto3/urllib3
    # threads are inherited. Set here, not at import -- at import it would
    # mutate global multiprocessing state for every importer, pytest included.
    mp.set_start_method("spawn", force=True)

    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )

    failed_tickers: list[str] = []
    for i, ticker in enumerate(TARGET_TICKERS, 1):
        cache_file = CHUNK_CACHE / f"{ticker}.json"
        if cache_file.exists():
            n = len(json.loads(cache_file.read_text()))
            print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: cached ({n} chunks)", flush=True)
            continue

        print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: ingesting ...", flush=True)
        try:
            count, chunks = bootstrap_ticker(s3_client, bedrock_client, pinecone_index, ticker)
        except Exception as e:
            # No cache file on failure -- the next run must retry this ticker
            # rather than skip it as already done.
            failed_tickers.append(ticker)
            print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: FAILED - {e}", flush=True)
            continue
        cache_file.write_text(json.dumps(chunks))
        print(f"[{i}/{len(TARGET_TICKERS)}] {ticker}: synced {count} chunks", flush=True)

    # BM25 must span the WHOLE corpus. Building it from only the tickers
    # ingested in this run is how the index ended up covering 29 of 50
    # companies after an interrupted bootstrap was resumed as a second run.
    corpus_chunks: list[dict[str, Any]] = []
    for ticker in TARGET_TICKERS:
        cache_file = CHUNK_CACHE / f"{ticker}.json"
        if cache_file.exists():
            corpus_chunks.extend(json.loads(cache_file.read_text()))

    covered = {c.get("ticker") for c in corpus_chunks}
    missing = set(TARGET_TICKERS) - covered

    # Publishing an index built from a partial run REPLACES the good one in
    # S3, silently shrinking retrieval coverage -- a failed run would leave
    # the corpus worse than before it started. Only publish on a full pass.
    if failed_tickers:
        print(
            f"\nSkipping BM25 publish: {len(failed_tickers)} ticker(s) failed, so an "
            f"index built now would cover only {len(covered)} companies and would "
            f"overwrite the existing one in S3."
        )
    else:
        build_and_store_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY, corpus_chunks)
        print(f"BM25 index built from {len(corpus_chunks)} chunks across {len(covered)} companies")

    if failed_tickers:
        print(f"\nFAILED ({len(failed_tickers)}): {sorted(failed_tickers)}")
        print("Re-run to retry them -- cached tickers are skipped.")
    if missing:
        print(f"NOT IN CORPUS ({len(missing)}): {sorted(missing)}")
    if failed_tickers or missing:
        sys.exit(1)
    print(f"\nComplete: all {len(TARGET_TICKERS)} tickers ingested.")


if __name__ == "__main__":
    main()

"""One-time bootstrap: ingest the initial 20-company corpus end to end.

Runs edgar_client -> html_processor -> chunker -> sync_pinecone for each
ticker in TARGET_TICKERS. Run once locally to seed the corpus before the
weekly refresh cron (Week 4+) takes over.
"""
from __future__ import annotations

import os
from typing import Any

import boto3

from pipeline.chunker import chunk_filing
from pipeline.edgar_client import download_filing, get_cik_for_ticker, list_filings, store_filing
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import get_pinecone_index, sync_chunks_to_pinecone

TARGET_TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",   # Tech
    "TSLA", "F", "GM", "RIVN", "LCID",         # EV/Auto
    "JPM", "BAC", "GS", "MS", "V",             # Finance
    "JNJ", "PFE", "UNH", "ABBV", "MRK",        # Healthcare
]

RAW_BUCKET = "finrag-raw-filings"


def bootstrap_ticker(
    s3_client: Any, bedrock_client: Any, pinecone_index: Any, ticker: str
) -> int:
    """Ingest, process, chunk, and sync one ticker's filings end to end.

    Args:
        s3_client: A boto3 S3 client.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        ticker: Stock ticker symbol to bootstrap.

    Returns:
        Number of chunks synced to Pinecone for this ticker.
    """
    cik = get_cik_for_ticker(ticker)
    filings = list_filings(ticker, cik)

    total_chunks = 0
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
            total_chunks += sync_chunks_to_pinecone(bedrock_client, pinecone_index, chunks)
        except Exception as e:
            print(f"{ticker} {filing.accession_number}: failed - {e}")
            continue

    return total_chunks


def main() -> None:
    """Bootstrap the full 20-company corpus."""
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )

    for ticker in TARGET_TICKERS:
        count = bootstrap_ticker(s3_client, bedrock_client, pinecone_index, ticker)
        print(f"{ticker}: synced {count} chunks")


if __name__ == "__main__":
    main()

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from pipeline.edgar_client import FilingMetadata
from scripts.bootstrap_corpus import (
    KNOWN_UNAVAILABLE,
    TARGET_TICKERS,
    bootstrap_ticker,
    main,
)


@patch("scripts.bootstrap_corpus.sync_chunks_to_pinecone")
@patch("scripts.bootstrap_corpus.chunk_filing")
@patch("scripts.bootstrap_corpus.process_filing")
@patch("scripts.bootstrap_corpus.store_filing")
@patch("scripts.bootstrap_corpus.download_filing")
@patch("scripts.bootstrap_corpus.list_filings")
@patch("scripts.bootstrap_corpus.get_cik_for_ticker")
def test_bootstrap_ticker_runs_full_pipeline_per_filing(
    mock_cik, mock_list, mock_download, mock_store, mock_process, mock_chunk, mock_sync
):
    mock_cik.return_value = 1045810
    filing = FilingMetadata(
        ticker="NVDA",
        cik=1045810,
        form_type="10-Q",
        filing_date="2026-08-01",
        accession_number="0001-26-000010",
        primary_document="nvda.htm",
    )
    mock_list.return_value = [filing]
    mock_download.return_value = b"<html>content</html>"
    mock_process.return_value = {"text_blocks": [], "tables": [], "metadata": {}}
    mock_chunk.return_value = [{"chunk_id": "c1", "text": "x"}]
    mock_sync.return_value = 1

    total, chunks = bootstrap_ticker(MagicMock(), MagicMock(), MagicMock(), "NVDA")

    assert total == 1
    assert chunks == [{"chunk_id": "c1", "text": "x"}]
    # NVDA is not a FinanceBench company, so it keeps the default shallow depth
    mock_list.assert_called_once_with("NVDA", 1045810, form_limits=None)
    mock_download.assert_called_once_with(filing)
    mock_sync.assert_called_once()


def test_target_tickers_has_no_duplicates():
    assert len(set(TARGET_TICKERS)) == len(TARGET_TICKERS)


def test_target_tickers_cover_every_financebench_company():
    """The benchmark is only meaningful if its companies are in the corpus.

    Without this, a question about a missing company still retrieves chunks --
    from whichever other company scored highest -- so the gap reads as a poor
    score rather than as missing data.
    """
    import json
    from pathlib import Path

    fb_path = Path(__file__).parent.parent.parent / "evals/eval_data/financebench_150.json"
    if not fb_path.exists():
        return  # dataset is downloaded in CI before the eval job

    # FinanceBench labels rows by company name; the corpus is keyed by ticker.
    name_to_ticker = {
        "3M": "MMM", "Activision Blizzard": "ATVI", "Adobe": "ADBE",
        "AES Corporation": "AES", "Amazon": "AMZN", "Amcor": "AMCR",
        "AMD": "AMD", "American Express": "AXP", "American Water Works": "AWK",
        "Best Buy": "BBY", "Block": "SQ", "Boeing": "BA", "Coca-Cola": "KO",
        "Corning": "GLW", "Costco": "COST", "CVS Health": "CVS",
        "Foot Locker": "FL", "General Mills": "GIS",
        "Johnson & Johnson": "JNJ", "JPMorgan": "JPM", "Kraft Heinz": "KHC",
        "Lockheed Martin": "LMT", "MGM Resorts": "MGM", "Microsoft": "MSFT",
        "Netflix": "NFLX", "Nike": "NKE", "Paypal": "PYPL", "PepsiCo": "PEP",
        "Pfizer": "PFE", "Ulta Beauty": "ULTA", "Verizon": "VZ", "Walmart": "WMT",
    }
    rows = json.loads(fb_path.read_text())
    needed = {name_to_ticker.get(r["ticker"], r["ticker"]) for r in rows}
    missing = needed - set(TARGET_TICKERS)
    assert not missing, f"FinanceBench companies absent from corpus: {sorted(missing)}"


@patch("scripts.bootstrap_corpus.build_and_store_keyword_index")
@patch("scripts.bootstrap_corpus.bootstrap_ticker")
@patch("scripts.bootstrap_corpus.get_pinecone_index")
@patch("scripts.bootstrap_corpus.boto3")
def test_main_builds_bm25_index_after_all_tickers(
    mock_boto3, mock_get_index, mock_bootstrap_ticker, mock_build_bm25, tmp_path
):
    mock_bootstrap_ticker.side_effect = lambda s3, br, idx, ticker: (
        5,
        [{"chunk_id": f"{ticker}-c1", "text": "x", "ticker": ticker}],
    )
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.bootstrap_corpus.CHUNK_CACHE", tmp_path / "chunks"):
        main()

    expected = len(TARGET_TICKERS) - len(KNOWN_UNAVAILABLE)
    assert mock_bootstrap_ticker.call_count == expected
    mock_build_bm25.assert_called_once()
    # BM25 must be built over every ticker's chunks, not just the last one's
    # a generator: consume it to check every ticker's chunks reached the index
    chunks_arg = list(mock_build_bm25.call_args[0][3])
    assert len(chunks_arg) == expected


@patch("scripts.bootstrap_corpus.build_and_store_keyword_index")
@patch("scripts.bootstrap_corpus.bootstrap_ticker")
@patch("scripts.bootstrap_corpus.get_pinecone_index")
@patch("scripts.bootstrap_corpus.boto3")
def test_partial_run_does_not_publish_bm25(
    mock_boto3, mock_get_index, mock_bootstrap_ticker, mock_build_bm25, tmp_path
):
    """Publishing an index from a partial run overwrites the good one in S3
    and silently shrinks retrieval coverage."""
    failing = TARGET_TICKERS[0]

    def maybe_fail(s3, br, idx, ticker):
        if ticker == failing:
            raise RuntimeError("simulated network drop")
        return 1, [{"chunk_id": f"{ticker}-c1", "text": "x", "ticker": ticker}]

    mock_bootstrap_ticker.side_effect = maybe_fail
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.bootstrap_corpus.CHUNK_CACHE", tmp_path / "chunks"):
        with pytest.raises(SystemExit):
            main()

    mock_build_bm25.assert_not_called()


@patch("scripts.bootstrap_corpus.build_and_store_keyword_index")
@patch("scripts.bootstrap_corpus.bootstrap_ticker")
@patch("scripts.bootstrap_corpus.get_pinecone_index")
@patch("scripts.bootstrap_corpus.boto3")
def test_main_resumes_from_cache_without_reingesting(
    mock_boto3, mock_get_index, mock_bootstrap_ticker, mock_build_bm25, tmp_path
):
    """A cached ticker must not be re-ingested -- that is the whole point of
    the cache after an interrupted run."""
    cache = tmp_path / "chunks"
    cache.mkdir()
    cached_ticker = TARGET_TICKERS[0]
    (cache / f"{cached_ticker}.json").write_text(
        json.dumps([{"chunk_id": "cached-1", "text": "x", "ticker": cached_ticker}])
    )
    mock_bootstrap_ticker.side_effect = lambda s3, br, idx, ticker: (
        1,
        [{"chunk_id": f"{ticker}-c1", "text": "x", "ticker": ticker}],
    )
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.bootstrap_corpus.CHUNK_CACHE", cache):
        main()

    expected = len(TARGET_TICKERS) - len(KNOWN_UNAVAILABLE) - 1  # -1 for the cached one
    assert mock_bootstrap_ticker.call_count == expected
    ingested = [c.args[3] for c in mock_bootstrap_ticker.call_args_list]
    assert cached_ticker not in ingested
    # A known-unavailable ticker must never be attempted -- it would embed
    # every filing via OpenAI before failing at upsert.
    assert not (set(ingested) & KNOWN_UNAVAILABLE.keys())

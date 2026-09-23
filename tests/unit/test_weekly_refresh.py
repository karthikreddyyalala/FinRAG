"""TDD: weekly refresh -- ingest only filings EDGAR added since last run.

bootstrap_corpus.py's cache is "ingested once, skip forever" -- correct for
a one-time seed, wrong for a recurring job: re-running it against an
already-seeded corpus would skip every ticker (cache file exists) and never
notice a new 10-Q. Blindly re-ingesting everything instead would re-embed
and re-upsert 2,000+ unchanged filings every week, burning OpenAI budget and
re-tripping the same Pinecone free-tier write cap that already cost a
FinanceBench question this project. Correct behavior: diff EDGAR's current
filing list against what's cached (by filing_date) and touch only the new
ones.
"""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from pipeline.edgar_client import FilingMetadata
from scripts.weekly_refresh import KNOWN_UNAVAILABLE, TARGET_TICKERS, handler, main, refresh_ticker

OLD_FILING = FilingMetadata(
    ticker="NVDA", cik=1045810, form_type="10-Q", filing_date="2026-05-01",
    accession_number="0001-26-000005", primary_document="old.htm",
)
NEW_FILING = FilingMetadata(
    ticker="NVDA", cik=1045810, form_type="10-Q", filing_date="2026-08-01",
    accession_number="0001-26-000010", primary_document="new.htm",
)


@patch("scripts.weekly_refresh.sync_chunks_to_pinecone")
@patch("scripts.weekly_refresh.chunk_filing")
@patch("scripts.weekly_refresh.process_filing")
@patch("scripts.weekly_refresh.store_filing")
@patch("scripts.weekly_refresh.download_filing")
@patch("scripts.weekly_refresh.list_filings")
@patch("scripts.weekly_refresh.get_cik_for_ticker")
def test_only_filings_newer_than_the_cache_are_ingested(
    mock_cik, mock_list, mock_download, mock_store, mock_process, mock_chunk, mock_sync
):
    """EDGAR's list includes a filing already in the cache (by filing_date)
    and one that isn't -- only the new one should hit download/embed/upsert."""
    mock_cik.return_value = 1045810
    mock_list.return_value = [OLD_FILING, NEW_FILING]
    mock_download.return_value = b"<html>new</html>"
    mock_process.return_value = {"text_blocks": [], "tables": [], "metadata": {}}
    mock_chunk.return_value = [{"chunk_id": "new-1", "text": "x", "period": "2026-08-01"}]
    mock_sync.return_value = 1
    cached_chunks = [{"chunk_id": "old-1", "text": "y", "period": "2026-05-01"}]

    new_count, merged = refresh_ticker(MagicMock(), MagicMock(), MagicMock(), "NVDA", cached_chunks)

    assert new_count == 1
    mock_download.assert_called_once_with(NEW_FILING)
    assert merged == cached_chunks + [{"chunk_id": "new-1", "text": "x", "period": "2026-08-01"}]


@patch("scripts.weekly_refresh.list_filings")
@patch("scripts.weekly_refresh.get_cik_for_ticker")
def test_no_new_filings_touches_nothing(mock_cik, mock_list):
    mock_cik.return_value = 1045810
    mock_list.return_value = [OLD_FILING]
    cached_chunks = [{"chunk_id": "old-1", "text": "y", "period": "2026-05-01"}]

    new_count, merged = refresh_ticker(MagicMock(), MagicMock(), MagicMock(), "NVDA", cached_chunks)

    assert new_count == 0
    assert merged is cached_chunks


@patch("scripts.weekly_refresh.sync_chunks_to_pinecone")
@patch("scripts.weekly_refresh.chunk_filing")
@patch("scripts.weekly_refresh.process_filing")
@patch("scripts.weekly_refresh.store_filing")
@patch("scripts.weekly_refresh.download_filing")
@patch("scripts.weekly_refresh.list_filings")
@patch("scripts.weekly_refresh.get_cik_for_ticker")
def test_a_failed_new_filing_raises_without_partial_cache_update(
    mock_cik, mock_list, mock_download, mock_store, mock_process, mock_chunk, mock_sync
):
    """Matches bootstrap_ticker's existing all-or-nothing discipline: writing
    a partial cache would mark a failed filing as done, so the next weekly
    run would never retry it."""
    mock_cik.return_value = 1045810
    mock_list.return_value = [NEW_FILING]
    mock_download.side_effect = RuntimeError("network drop")

    with pytest.raises(RuntimeError):
        refresh_ticker(MagicMock(), MagicMock(), MagicMock(), "NVDA", [])


def test_target_tickers_reused_from_bootstrap_corpus():
    """Must stay in sync with the seeded corpus, not drift into its own list."""
    from scripts.bootstrap_corpus import TARGET_TICKERS as BOOTSTRAP_TICKERS

    assert TARGET_TICKERS == BOOTSTRAP_TICKERS


@patch("scripts.weekly_refresh.build_and_store_keyword_index")
@patch("scripts.weekly_refresh.refresh_ticker")
@patch("scripts.weekly_refresh.get_pinecone_index")
@patch("scripts.weekly_refresh.boto3")
def test_main_rebuilds_index_only_when_something_changed(
    mock_boto3, mock_get_index, mock_refresh, mock_build, tmp_path
):
    mock_refresh.side_effect = lambda s3, br, idx, ticker, cached: (0, cached)
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.weekly_refresh.CHUNK_CACHE", tmp_path / "chunks"):
        main()

    mock_build.assert_not_called()


@patch("scripts.weekly_refresh.build_and_store_keyword_index")
@patch("scripts.weekly_refresh.refresh_ticker")
@patch("scripts.weekly_refresh.get_pinecone_index")
@patch("scripts.weekly_refresh.boto3")
def test_main_rebuilds_index_when_a_ticker_got_new_chunks(
    mock_boto3, mock_get_index, mock_refresh, mock_build, tmp_path
):
    """Coverage must reflect the already-seeded corpus (every ticker already
    has a cache file from bootstrap_corpus), not an empty tmp dir -- only
    one ticker actually changing shouldn't read as 71 newly uncovered."""
    cache = tmp_path / "chunks"
    cache.mkdir()
    for ticker in TARGET_TICKERS:
        if ticker not in KNOWN_UNAVAILABLE:
            (cache / f"{ticker}.json").write_text(
                json.dumps([{"chunk_id": f"{ticker}-seed", "text": "x", "ticker": ticker}])
            )
    first_ticker = TARGET_TICKERS[0]

    def side_effect(s3, br, idx, ticker, cached):
        if ticker == first_ticker:
            return 1, [*cached, {"chunk_id": f"{ticker}-new", "text": "y", "ticker": ticker}]
        return 0, cached

    mock_refresh.side_effect = side_effect
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.weekly_refresh.CHUNK_CACHE", cache):
        main()

    mock_build.assert_called_once()


@patch("scripts.weekly_refresh.refresh_ticker")
@patch("scripts.weekly_refresh.get_pinecone_index")
@patch("scripts.weekly_refresh.boto3")
def test_main_exits_nonzero_on_any_failure(mock_boto3, mock_get_index, mock_refresh, tmp_path):
    failing = TARGET_TICKERS[0]

    def side_effect(s3, br, idx, ticker, cached):
        if ticker == failing:
            raise RuntimeError("simulated failure")
        return 0, cached

    mock_refresh.side_effect = side_effect
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.weekly_refresh.CHUNK_CACHE", tmp_path / "chunks"):
        with pytest.raises(SystemExit):
            main()


def test_known_unavailable_tickers_never_attempted():
    assert set(KNOWN_UNAVAILABLE) & set(TARGET_TICKERS) == set(KNOWN_UNAVAILABLE)


@patch("scripts.weekly_refresh.main")
@patch("scripts.weekly_refresh.load_secrets_from_ssm")
@patch("scripts.weekly_refresh.boto3")
def test_handler_loads_secrets_then_refreshes(mock_boto3, mock_load_secrets, mock_main):
    handler({}, MagicMock())

    mock_load_secrets.assert_called_once()
    mock_main.assert_called_once()


@patch("scripts.weekly_refresh.build_and_store_keyword_index")
@patch("scripts.weekly_refresh.refresh_ticker")
@patch("scripts.weekly_refresh.get_pinecone_index")
@patch("scripts.weekly_refresh.boto3")
def test_main_never_calls_refresh_on_a_known_unavailable_ticker(
    mock_boto3, mock_get_index, mock_refresh, mock_build, tmp_path
):
    mock_refresh.side_effect = lambda s3, br, idx, ticker, cached: (0, cached)
    os.environ["PINECONE_API_KEY"] = "test-key"

    with patch("scripts.weekly_refresh.CHUNK_CACHE", tmp_path / "chunks"):
        main()

    attempted = {c.args[3] for c in mock_refresh.call_args_list}
    assert not (attempted & set(KNOWN_UNAVAILABLE))

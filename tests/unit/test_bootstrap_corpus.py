import os
from unittest.mock import MagicMock, patch

from pipeline.edgar_client import FilingMetadata
from scripts.bootstrap_corpus import TARGET_TICKERS, bootstrap_ticker, main


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
    mock_list.assert_called_once_with("NVDA", 1045810)
    mock_download.assert_called_once_with(filing)
    mock_sync.assert_called_once()


def test_target_tickers_has_exactly_fifty_companies():
    assert len(TARGET_TICKERS) == 50
    assert len(set(TARGET_TICKERS)) == 50  # no duplicates


@patch("scripts.bootstrap_corpus.build_and_store_bm25_index")
@patch("scripts.bootstrap_corpus.bootstrap_ticker")
@patch("scripts.bootstrap_corpus.get_pinecone_index")
@patch("scripts.bootstrap_corpus.boto3")
def test_main_builds_bm25_index_after_all_tickers(
    mock_boto3, mock_get_index, mock_bootstrap_ticker, mock_build_bm25
):
    mock_bootstrap_ticker.return_value = (5, [{"chunk_id": "c1", "text": "x"}])
    os.environ["PINECONE_API_KEY"] = "test-key"

    main()

    assert mock_bootstrap_ticker.call_count == len(TARGET_TICKERS)
    mock_build_bm25.assert_called_once()

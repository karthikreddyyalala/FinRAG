"""TDD: get_latest_filing -- metadata lookup + brief summary, no RAG pipeline.

Spec (CLAUDE.md Tool 4): ticker + filing_type in, most-recent-filing metadata
+ 3-sentence executive summary out. Flow: "metadata lookup + brief
summarization, no full RAG pipeline" -- metadata comes straight from EDGAR
(live, authoritative, not from our corpus which may lag), and the summary is
one cheap Haiku call over whatever corpus chunks exist for that filing, not
the four-stage rewrite/hybrid/rerank pipeline the other three tools run.
"""
from unittest.mock import MagicMock, patch

from pipeline.edgar_client import FilingMetadata
from server.mcp_tools.get_latest_filing import build_latest_filing_answer

FILING = FilingMetadata(
    ticker="AAPL", cik=320193, form_type="10-Q", filing_date="2026-08-01",
    accession_number="0000320193-26-000050", primary_document="aapl-20260627.htm",
)


def test_metadata_comes_from_live_edgar_not_the_corpus():
    """Metadata must be fresh -- the corpus can lag EDGAR by up to a week
    (weekly refresh cron), so a lookup here has to hit EDGAR directly rather
    than reading whatever's cached in our keyword index."""
    keyword_index = MagicMock()
    keyword_index.search.return_value = []

    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker", return_value=320193) as mock_cik,
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[FILING]) as mock_list,
    ):
        result = build_latest_filing_answer(
            ticker="AAPL", filing_type="10-Q",
            bedrock_client=MagicMock(), keyword_index=keyword_index,
        )

    mock_cik.assert_called_once_with("AAPL")
    mock_list.assert_called_once_with("AAPL", 320193, form_limits={"10-Q": 1})
    assert result["filing"]["form_type"] == "10-Q"
    assert result["filing"]["filing_date"] == "2026-08-01"
    assert result["filing"]["accession_number"] == "0000320193-26-000050"


def test_summarizes_via_haiku_not_sonnet():
    """This is explicitly the cheap/brief path -- CLAUDE.md distinguishes it
    from the other three tools' full Sonnet generation. Using Sonnet here
    would be paying for reasoning depth a 3-sentence blurb doesn't need."""
    keyword_index = MagicMock()
    keyword_index.search.return_value = [
        {"chunk_id": "c1", "text": "Apple reported record services revenue.", "ticker": "AAPL"}
    ]
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "Apple's Q3 filing highlights record services revenue."}]}}
    }

    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker", return_value=320193),
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[FILING]),
    ):
        result = build_latest_filing_answer(
            ticker="AAPL", filing_type="10-Q",
            bedrock_client=bedrock, keyword_index=keyword_index,
        )

    assert "haiku" in bedrock.converse.call_args.kwargs["modelId"].lower()
    assert "services revenue" in result["summary"]


def test_no_ingested_chunks_skips_llm_call_entirely():
    """A brand-new filing EDGAR has but the corpus hasn't ingested yet must
    not silently hallucinate a summary from nothing -- and shouldn't spend
    an LLM call producing "I don't know" either."""
    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    bedrock = MagicMock()

    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker", return_value=320193),
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[FILING]),
    ):
        result = build_latest_filing_answer(
            ticker="AAPL", filing_type="10-Q",
            bedrock_client=bedrock, keyword_index=keyword_index,
        )

    bedrock.converse.assert_not_called()
    assert "not yet been ingested" in result["summary"]


def test_no_matching_filing_raises():
    keyword_index = MagicMock()
    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker", return_value=320193),
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[]),
    ):
        try:
            build_latest_filing_answer(
                ticker="AAPL", filing_type="10-Q",
                bedrock_client=MagicMock(), keyword_index=keyword_index,
            )
            raised = False
        except ValueError:
            raised = True
    assert raised


def test_registers_as_an_mcp_tool():
    from mcp.server import MCPServer

    from server.mcp_tools.get_latest_filing import register_get_latest_filing_tool

    mcp = MCPServer("Test")
    register_get_latest_filing_tool(mcp, MagicMock(), MagicMock())

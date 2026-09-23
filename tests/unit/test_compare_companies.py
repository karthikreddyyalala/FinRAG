"""TDD: compare_companies -- multi-hop lookup, one hop per ticker.

Spec (CLAUDE.md Tool 3): tickers list + metric + period in, side-by-side
comparison with per-company citations, "multi-hop retrieval (separate query
per company, merged answer)". Reuses get_financials.build_financials_answer
per ticker rather than reimplementing the lookup.
"""
from unittest.mock import MagicMock, patch

from server.mcp_tools.compare_companies import build_comparison_answer

TSLA_RESULT = {
    "ticker": "TSLA", "metric": "gross margin", "period": "2024",
    "answer": "Tesla's gross margin was 18.2%.",
    "citations": [{"ticker": "TSLA", "filing_type": "10-K", "period": "2024", "page": None, "text": "..."}],
    "cost_usd": 0.0, "latency_ms": 100,
}
FORD_RESULT = {
    "ticker": "F", "metric": "gross margin", "period": "2024",
    "answer": "Ford's gross margin was 9.1%.",
    "citations": [{"ticker": "F", "filing_type": "10-K", "period": "2024", "page": None, "text": "..."}],
    "cost_usd": 0.0, "latency_ms": 120,
}


def test_runs_one_lookup_per_ticker():
    with patch(
        "server.mcp_tools.compare_companies.build_financials_answer",
        side_effect=[TSLA_RESULT, FORD_RESULT],
    ) as mock_lookup:
        build_comparison_answer(
            tickers=["TSLA", "F"], metric="gross margin", period="2024",
            bedrock_client=MagicMock(), pinecone_index=MagicMock(),
            keyword_index=MagicMock(), embed_fn=lambda t: [0.0],
        )

    assert mock_lookup.call_count == 2
    called_tickers = [c.kwargs.get("ticker", c.args[0] if c.args else None) for c in mock_lookup.call_args_list]
    assert called_tickers == ["TSLA", "F"]


def test_returns_side_by_side_structure():
    with patch(
        "server.mcp_tools.compare_companies.build_financials_answer",
        side_effect=[TSLA_RESULT, FORD_RESULT],
    ):
        result = build_comparison_answer(
            tickers=["TSLA", "F"], metric="gross margin", period="2024",
            bedrock_client=MagicMock(), pinecone_index=MagicMock(),
            keyword_index=MagicMock(), embed_fn=lambda t: [0.0],
        )

    assert result["metric"] == "gross margin"
    assert result["period"] == "2024"
    assert len(result["companies"]) == 2
    assert result["companies"][0]["ticker"] == "TSLA"
    assert "18.2%" in result["companies"][0]["answer"]
    assert result["companies"][0]["citations"] == TSLA_RESULT["citations"]
    assert result["companies"][1]["ticker"] == "F"
    assert "latency_ms" in result


def test_one_ticker_failing_does_not_drop_the_others():
    """A single bad ticker (typo, unignested company) must not blank the
    whole comparison -- the other companies' lookups already succeeded."""
    def side_effect(ticker, metric, period, **kwargs):
        if ticker == "ZZZZ":
            raise RuntimeError("no chunks for ticker")
        return TSLA_RESULT

    with patch(
        "server.mcp_tools.compare_companies.build_financials_answer",
        side_effect=side_effect,
    ):
        result = build_comparison_answer(
            tickers=["TSLA", "ZZZZ"], metric="gross margin", period="2024",
            bedrock_client=MagicMock(), pinecone_index=MagicMock(),
            keyword_index=MagicMock(), embed_fn=lambda t: [0.0],
        )

    assert result["companies"][0]["ticker"] == "TSLA"
    assert result["companies"][1]["ticker"] == "ZZZZ"
    assert "error" in result["companies"][1]


def test_registers_as_an_mcp_tool():
    from mcp.server import MCPServer

    from server.mcp_tools.compare_companies import register_compare_companies_tool

    mcp = MCPServer("Test")
    register_compare_companies_tool(mcp, MagicMock(), MagicMock(), MagicMock(), lambda t: [0.0])

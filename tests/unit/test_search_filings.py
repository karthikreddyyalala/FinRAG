from unittest.mock import MagicMock

from mcp.server import MCPServer

from server.mcp_tools.search_filings import (
    build_search_filings_answer,
    register_search_filings_tool,
)


def _fake_pinecone_index(matches):
    index = MagicMock()
    index.query.return_value = {"matches": matches}
    return index


def test_build_search_filings_answer_returns_citations_from_matches():
    matches = [
        {
            "id": "chunk-1",
            "metadata": {
                "ticker": "NVDA",
                "filing_type": "10-Q",
                "period": "Q1-2026",
                "page_number": None,
                "text": "Data center revenue grew significantly year over year.",
            },
        }
    ]
    index = _fake_pinecone_index(matches)
    embed_fn = MagicMock(return_value=[0.1, 0.2, 0.3])

    result = build_search_filings_answer("Nvidia data center revenue?", index, embed_fn)

    assert result["citations"] == [
        {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page": None}
    ]
    assert "Data center revenue grew" in result["answer"]
    assert result["cost_usd"] == 0.0
    assert isinstance(result["latency_ms"], int)
    embed_fn.assert_called_once_with("Nvidia data center revenue?")
    index.query.assert_called_once()


def test_register_search_filings_tool_does_not_raise():
    mcp = MCPServer("Test")
    index = _fake_pinecone_index([])
    embed_fn = MagicMock(return_value=[0.0])

    register_search_filings_tool(mcp, index, embed_fn)

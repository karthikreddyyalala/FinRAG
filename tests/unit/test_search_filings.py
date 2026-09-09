from unittest.mock import MagicMock, patch

from mcp.server import MCPServer

from server.mcp_tools.search_filings import (
    build_search_filings_answer,
    register_search_filings_tool,
)


def _deps():
    bedrock_client = MagicMock()
    bedrock_client.converse.side_effect = [
        {"output": {"message": {"content": [{"text": "NVDA data center revenue Q1 2026"}]}}},
        {"output": {"message": {"content": [{"text": "Revenue grew [NVDA 10-Q Q1-2026]."}]}}},
    ]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    bm25_index = MagicMock()
    bm25_index.get_scores.return_value = []
    bm25_chunks: list[dict] = []
    embed_fn = MagicMock(return_value=[0.1, 0.2])
    return bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn


@patch("server.mcp_tools.search_filings.rerank")
def test_build_search_filings_answer_runs_full_pipeline(mock_rerank):
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = _deps()
    mock_rerank.return_value = [
        {
            "chunk_id": "c1",
            "text": "Data center revenue reached $9.06 billion.",
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]

    query = "How did Nvidia data center revenue change?"
    result = build_search_filings_answer(
        query,
        bedrock_client=bedrock_client,
        pinecone_index=pinecone_index,
        bm25_index=bm25_index,
        bm25_chunks=bm25_chunks,
        embed_fn=embed_fn,
    )

    assert "Revenue grew" in result["answer"]
    assert result["citations"] == [
        {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page": None}
    ]
    assert isinstance(result["latency_ms"], int)
    # Pin the ORIGINAL query, not the rewritten one, reaching rerank --
    # CrossEncoder is trained on natural queries (see reranker.rerank's
    # docstring), so a future refactor swapping in `rewritten` here would
    # be a silent regression without this assertion.
    mock_rerank.assert_called_once_with(query, [], top_k=5)


@patch("server.mcp_tools.search_filings.rerank")
def test_register_search_filings_tool_does_not_raise(mock_rerank):
    mock_rerank.return_value = []
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = _deps()
    mcp = MCPServer("Test")

    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
    )

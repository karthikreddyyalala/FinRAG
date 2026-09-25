from unittest.mock import MagicMock, patch

import pytest
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
    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    embed_fn = MagicMock(return_value=[0.1, 0.2])
    return bedrock_client, pinecone_index, keyword_index, embed_fn


@patch("server.mcp_tools.search_filings.rerank")
def test_build_search_filings_answer_runs_full_pipeline(mock_rerank):
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
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
        keyword_index=keyword_index,
        embed_fn=embed_fn,
    )

    assert "Revenue grew" in result["answer"]
    # `text` is load-bearing: the eval harness reads citations[].text as the
    # ragas `contexts` field. Dropping it silently zeroes every context metric.
    assert result["citations"] == [
        {
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page": None,
            "text": "Data center revenue reached $9.06 billion.",
        }
    ]
    assert isinstance(result["latency_ms"], int)
    # Pin the ORIGINAL query, not the rewritten one, reaching rerank --
    # CrossEncoder is trained on natural queries (see reranker.rerank's
    # docstring), so a future refactor swapping in `rewritten` here would
    # be a silent regression without this assertion.
    # CrossEncoder gets the natural query; the lexical fallback gets the
    # GAAP-expanded rewrite, without which it discards table chunks whose
    # wording shares no terms with the question.
    mock_rerank.assert_called_once_with(
        query,
        [],
        top_k=5,
        lexical_query="NVDA data center revenue Q1 2026 net sales total revenues",
    )


@patch("server.mcp_tools.search_filings.rerank")
def test_register_search_filings_tool_does_not_raise(mock_rerank):
    mock_rerank.return_value = []
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mcp = MCPServer("Test")

    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, keyword_index, embed_fn
    )


@patch("server.mcp_tools.search_filings.rerank", return_value=[])
@patch("server.mcp_tools.search_filings.generate_answer", return_value="none")
@patch("server.mcp_tools.search_filings.rewrite_query", return_value="rewritten")
@patch("server.mcp_tools.search_filings.hybrid_search", return_value=[])
def test_company_and_year_from_the_question_become_retrieval_filters(
    mock_hybrid, mock_rewrite, mock_generate, mock_rerank
):
    """Live bug: "3M capital expenditure FY2018" missed the FY2018 10-K
    because 27 other MMM filings had look-alike PP&E rows."""
    from server.mcp_tools.search_filings import build_search_filings_answer

    build_search_filings_answer(
        "3M capital expenditure FY2018", MagicMock(), MagicMock(), MagicMock(), lambda t: [0.0]
    )

    kwargs = mock_hybrid.call_args.kwargs
    assert kwargs["ticker"] == "MMM"
    assert kwargs["period_range"] == ("2018-01-01", "2019-12-31")


@patch("server.mcp_tools.search_filings.rewrite_query")
@patch("server.mcp_tools.search_filings.rerank")
def test_dense_only_mode_skips_rewrite_and_rerank(mock_rerank, mock_rewrite):
    """Baseline A (CLAUDE.md Phase 4): dense search only, no rewrite, no rerank."""
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    pinecone_index.query.return_value = {
        "matches": [{"id": "c1", "metadata": {
            "text": "Revenue was $9.06B.", "ticker": "NVDA",
            "filing_type": "10-Q", "period": "Q1-2026",
        }}]
    }
    bedrock_client.converse.side_effect = [
        {"output": {"message": {"content": [{"text": "Revenue was $9.06B [NVDA 10-Q]."}]}}}
    ]

    result = build_search_filings_answer(
        "Nvidia revenue", bedrock_client, pinecone_index, keyword_index, embed_fn,
        mode="dense_only",
    )

    mock_rewrite.assert_not_called()
    mock_rerank.assert_not_called()
    keyword_index.search.assert_not_called()
    assert result["citations"] == [
        {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page": None,
         "text": "Revenue was $9.06B."}
    ]


@patch("server.mcp_tools.search_filings.rewrite_query")
@patch("server.mcp_tools.search_filings.rerank")
def test_bm25_only_mode_skips_rewrite_rerank_and_dense(mock_rerank, mock_rewrite):
    """Baseline B (CLAUDE.md Phase 4): BM25 only, no dense, no rewrite, no rerank."""
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    keyword_index.search.return_value = [
        {"chunk_id": "c1", "text": "Revenue was $9.06B.", "ticker": "NVDA",
         "filing_type": "10-Q", "period": "Q1-2026"}
    ]
    bedrock_client.converse.side_effect = [
        {"output": {"message": {"content": [{"text": "Revenue was $9.06B [NVDA 10-Q]."}]}}}
    ]

    result = build_search_filings_answer(
        "Nvidia revenue", bedrock_client, pinecone_index, keyword_index, embed_fn,
        mode="bm25_only",
    )

    mock_rewrite.assert_not_called()
    mock_rerank.assert_not_called()
    pinecone_index.query.assert_not_called()
    assert result["citations"][0]["text"] == "Revenue was $9.06B."


@patch("server.mcp_tools.search_filings.rerank")
def test_full_pipeline_returns_nonzero_cost_and_per_stage_latency(mock_rerank):
    """Phase C (CLAUDE.md): cost_usd must no longer be the Week 1-3 stub."""
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = [
        {"chunk_id": "c1", "text": "Data center revenue reached $9.06 billion.",
         "ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}
    ]

    result = build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client, pinecone_index, keyword_index, embed_fn,
    )

    assert result["cost_usd"] > 0.0


@patch("server.mcp_tools.search_filings.rerank")
def test_full_pipeline_logs_to_dynamodb_when_resource_given(mock_rerank):
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = [
        {"chunk_id": "c1", "text": "Data center revenue reached $9.06 billion.",
         "ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}
    ]
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table

    build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client, pinecone_index, keyword_index, embed_fn,
        dynamodb_resource=dynamodb,
    )

    dynamodb.Table.assert_called_once_with("finrag-query-logs")
    table.put_item.assert_called_once()


@patch("server.mcp_tools.search_filings.rerank")
def test_full_pipeline_skips_logging_when_no_dynamodb_resource(mock_rerank):
    """None (the default) must be a true no-op -- every eval/test call site
    that doesn't pass dynamodb_resource must keep working unchanged."""
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = []

    result = build_search_filings_answer(
        "q", bedrock_client, pinecone_index, keyword_index, embed_fn,
    )

    assert "cost_usd" in result  # ran to completion, no crash, nothing to assert on a mock


def test_unknown_mode_raises():
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    with pytest.raises(ValueError):
        build_search_filings_answer(
            "q", bedrock_client, pinecone_index, keyword_index, embed_fn, mode="bogus"
        )

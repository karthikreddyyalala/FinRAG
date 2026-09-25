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


def _dynamodb_with_separate_tables():
    """A dynamodb resource that routes .Table("name") to distinct mocks,
    so cache and log writes can be asserted independently. A cache miss on
    the cache table's get_item comes from a bare MagicMock() return value
    (no "Item" key) by construction of Mock's own .get(...) semantics --
    explicit here so cache-hit tests below can override it."""
    tables: dict[str, MagicMock] = {}

    def _table(name):
        if name not in tables:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # real DynamoDB miss shape
            tables[name] = mock_table
        return tables[name]

    dynamodb = MagicMock()
    dynamodb.Table.side_effect = _table
    return dynamodb, tables


@patch("server.mcp_tools.search_filings.rerank")
def test_full_pipeline_logs_to_dynamodb_when_resource_given(mock_rerank):
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = [
        {"chunk_id": "c1", "text": "Data center revenue reached $9.06 billion.",
         "ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}
    ]
    dynamodb, tables = _dynamodb_with_separate_tables()

    build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client, pinecone_index, keyword_index, embed_fn,
        dynamodb_resource=dynamodb,
    )

    tables["finrag-query-logs"].put_item.assert_called_once()
    assert tables["finrag-query-logs"].put_item.call_args.kwargs["Item"]["cache_hit"] is False


@patch("server.mcp_tools.search_filings.rerank")
def test_cache_miss_writes_answer_to_cache_table(mock_rerank):
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = [
        {"chunk_id": "c1", "text": "Data center revenue reached $9.06 billion.",
         "ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}
    ]
    dynamodb, tables = _dynamodb_with_separate_tables()

    result = build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client, pinecone_index, keyword_index, embed_fn,
        dynamodb_resource=dynamodb,
    )

    tables["finrag-query-cache"].get_item.assert_called_once()
    tables["finrag-query-cache"].put_item.assert_called_once()
    cached_item = tables["finrag-query-cache"].put_item.call_args.kwargs["Item"]
    assert cached_item["answer"] == result["answer"]
    assert result["cost_usd"] > 0.0  # real pipeline ran, not served from cache


@patch("server.mcp_tools.search_filings.rerank")
def test_cache_hit_skips_pipeline_and_returns_zero_cost(mock_rerank):
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    dynamodb, tables = _dynamodb_with_separate_tables()
    dynamodb.Table("finrag-query-cache")  # force lazy creation before overriding get_item below
    tables["finrag-query-cache"].get_item.return_value = {
        "Item": {
            "answer": "cached answer [NVDA 10-Q Q1-2026].",
            "citations": [{"ticker": "NVDA"}],
            "ttl": int(__import__("time").time()) + 3600,
        }
    }

    result = build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client, pinecone_index, keyword_index, embed_fn,
        dynamodb_resource=dynamodb,
    )

    assert result["answer"] == "cached answer [NVDA 10-Q Q1-2026]."
    assert result["cost_usd"] == 0.0
    mock_rerank.assert_not_called()  # pipeline never ran
    bedrock_client.converse.assert_not_called()  # no rewrite/generate calls made
    tables["finrag-query-cache"].put_item.assert_not_called()  # no re-write of an existing hit
    log_item = tables["finrag-query-logs"].put_item.call_args.kwargs["Item"]
    assert log_item["cache_hit"] is True
    assert log_item["cost_usd"] == 0


@patch("server.mcp_tools.search_filings.rerank")
def test_baseline_modes_never_touch_the_cache(mock_rerank):
    """dense_only/bm25_only exist to measure the UNCACHED pipeline for
    evals/run_eval.py's baseline comparison -- a cache hit here would
    silently corrupt that measurement."""
    bedrock_client, pinecone_index, keyword_index, embed_fn = _deps()
    mock_rerank.return_value = []
    dynamodb, tables = _dynamodb_with_separate_tables()

    build_search_filings_answer(
        "q", bedrock_client, pinecone_index, keyword_index, embed_fn,
        mode="dense_only", dynamodb_resource=dynamodb,
    )

    assert "finrag-query-cache" not in tables


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

"""TDD: get_company_financials -- targeted single-metric lookup.

Spec (CLAUDE.md Tool 2): ticker+metric+period in, structured value + citation
out, "targeted retrieval" -- unlike search_sec_filings this skips the Haiku
query-rewrite call (the query is already structured, nothing to expand from
natural language) and goes straight to the same GAAP-expansion + hybrid
search + rerank + verify stages.
"""
from unittest.mock import MagicMock, patch

from server.mcp_tools.get_financials import build_financials_answer

CHUNK = {
    "chunk_id": "c1",
    "text": "Purchases of property, plant and equipment (PP&E) $ (1,577)",
    "ticker": "MMM",
    "filing_type": "10-K",
    "period": "2019-02-07",
    "page_number": None,
}


def test_skips_the_haiku_rewrite_call():
    """The query is already structured (ticker/metric/period) -- nothing for
    an LLM to expand from natural language. Calling Haiku here is a wasted
    API call and adds latency for no benefit."""
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "$(1,577) million [MMM 10-K 2019-02-07]"}]}}
    }
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]):
        build_financials_answer(
            ticker="MMM", metric="capital expenditure", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    rewrite_calls = [
        c for c in bedrock.converse.call_args_list
        if "haiku" in str(c.kwargs.get("modelId", "")).lower()
    ]
    assert not rewrite_calls, "Haiku rewrite was called for a structured lookup"


def test_query_text_carries_gaap_expansion():
    """"capital expenditure" must reach the retrieval query as GAAP wording
    too, or this tool inherits the exact vocabulary-gap bug search_sec_filings
    had before GAAP_SYNONYMS existed."""
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "$(1,577) million"}]}}
    }
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]) as mock_rerank:
        build_financials_answer(
            ticker="MMM", metric="capital expenditure", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    lexical_query = mock_rerank.call_args.kwargs.get("lexical_query", "")
    assert "property" in lexical_query.lower() and "equipment" in lexical_query.lower()


def test_returns_structured_result_with_citation():
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "3M's FY2018 capex was $(1,577) million."}]}}
    }
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]):
        result = build_financials_answer(
            ticker="MMM", metric="capital expenditure", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    assert result["ticker"] == "MMM"
    assert result["metric"] == "capital expenditure"
    assert result["period"] == "FY2018"
    assert "1,577" in result["answer"]
    assert result["citations"][0]["ticker"] == "MMM"
    assert "latency_ms" in result


def test_ungrounded_figure_is_still_caught():
    """The numerical verifier must run here exactly as it does in
    search_sec_filings -- this tool is not exempt from the grounding guarantee."""
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "3M's FY2018 capex was $9,999 million."}]}}
    }
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]):
        result = build_financials_answer(
            ticker="MMM", metric="capital expenditure", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    assert "unavailable" in result["answer"]


def test_cross_ticker_candidates_are_filtered_before_rerank():
    """Caught live: compare_companies(["TSLA", "F"], "revenue", "2024") cited
    Ford's revenue to a Pfizer 10-K -- a real number from the wrong company,
    stated with full confidence. Root cause: "F" is too weak a lexical token
    to constrain BM25/dense retrieval to Ford, so an unrelated PFE chunk rode
    along in the candidate set. The ticker is known up front for this tool
    (unlike search_sec_filings' free-text queries), so candidates must be
    filtered to it before reranking, not trusted to retrieval alone."""
    pfizer_chunk = {
        **CHUNK, "chunk_id": "c2", "ticker": "PFE", "text": "Pfizer revenue $63.6 billion"
    }
    bedrock = MagicMock()
    bedrock.converse.return_value = {"output": {"message": {"content": [{"text": "ok"}]}}}
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK, pfizer_chunk]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]) as mock_rerank:
        build_financials_answer(
            ticker="MMM", metric="revenue", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    candidates_passed = mock_rerank.call_args.args[1]
    assert all(c["ticker"] == "MMM" for c in candidates_passed)


def test_registers_as_an_mcp_tool():
    from mcp.server import MCPServer

    from server.mcp_tools.get_financials import register_get_financials_tool

    mcp = MCPServer("Test")
    register_get_financials_tool(mcp, MagicMock(), MagicMock(), MagicMock(), lambda t: [0.0])
    # no exception -> registered without raising


def test_ticker_and_period_become_retrieval_filters():
    with (
        patch("server.mcp_tools.get_financials.hybrid_search", return_value=[]) as mock_hybrid,
        patch("server.mcp_tools.get_financials.rerank", return_value=[]),
        patch("server.mcp_tools.get_financials.generate_answer", return_value="none"),
    ):
        build_financials_answer(
            ticker="mmm", metric="capital expenditure", period="FY2018",
            bedrock_client=MagicMock(), pinecone_index=MagicMock(),
            keyword_index=MagicMock(), embed_fn=lambda t: [0.0],
        )

    kwargs = mock_hybrid.call_args.kwargs
    assert kwargs["ticker"] == "MMM"
    assert kwargs["period_range"] == ("2018-01-01", "2019-12-31")


def test_returns_nonzero_cost_usd():
    """Phase C (CLAUDE.md): cost_usd must no longer be the Week 1-3 stub."""
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "output": {"message": {"content": [{"text": "$(1,577) million [MMM 10-K 2019-02-07]"}]}}
    }
    keyword_index = MagicMock()
    keyword_index.search.return_value = [CHUNK]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}

    with patch("server.mcp_tools.get_financials.rerank", return_value=[CHUNK]):
        result = build_financials_answer(
            ticker="MMM", metric="capital expenditure", period="FY2018",
            bedrock_client=bedrock, pinecone_index=pinecone_index,
            keyword_index=keyword_index, embed_fn=lambda t: [0.0],
        )

    assert result["cost_usd"] > 0.0

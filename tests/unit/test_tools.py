from unittest.mock import patch

from pipeline.edgar_client import FilingMetadata
from server.mcp_tools.common import Deps
from server.mcp_tools.compare_companies import register_compare_companies_tool
from server.mcp_tools.get_financials import register_get_financials_tool
from server.mcp_tools.get_latest_filing import register_get_latest_filing_tool
from server.mcp_tools.list_covered_companies import register_list_covered_companies_tool
from server.mcp_tools.search_filings import register_search_filings_tool
from server.mcp_tools.verify_figures import register_verify_figures_tool
from tests.unit.mcp_helpers import FakeKeywordIndex, chunk, pinecone_returning, tool_client

ALL = (
    register_search_filings_tool, register_get_financials_tool, register_compare_companies_tool,
    register_get_latest_filing_tool, register_list_covered_companies_tool,
    register_verify_figures_tool,
)
CAPEX = chunk("a1", "Purchases of property, plant and equipment (PP&E) (1,577) (1,373)")
REVENUE = chunk("n1", "Revenue 44,062 26,044", ticker="NVDA", filing_type="10-Q",
                period="2025-05-28", page=None)


def _deps(chunks=(CAPEX, REVENUE)):
    return Deps(pinecone_returning([]), FakeKeywordIndex(list(chunks)), lambda t: [0.1], None)


def test_search_returns_cited_passages():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, result = call("search_sec_filings",
                                {"question": "3M capital expenditure", "ticker": "mmm"})
    assert not is_error
    assert result["passages"][0]["id"] == "a1"
    assert result["passages"][0]["citation"] == "[MMM 10-K 2019-02-07 p.40]"


def test_search_rejects_an_uncovered_ticker_with_a_useful_message():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("search_sec_filings", {"question": "capex", "ticker": "ZZZ"})
    assert is_error
    assert "ZZZ is not in FinRAG's corpus" in text and "list_covered_companies" in text


def test_search_rejects_an_oversized_question():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("search_sec_filings", {"question": "x" * 501})
    assert is_error and "limit is 500" in text


def test_search_rejects_an_empty_question():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("search_sec_filings", {"question": "   "})
    assert is_error and "empty" in text


def test_get_company_financials_echoes_the_lookup_and_returns_passages():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, result = call("get_company_financials",
                                {"ticker": "MMM", "metric": "capital expenditure",
                                 "period": "FY2018"})
    assert not is_error
    assert (result["ticker"], result["metric"], result["period"]) == (
        "MMM", "capital expenditure", "FY2018")
    assert [p["id"] for p in result["passages"]] == ["a1"]


def test_compare_reports_an_uncovered_company_without_failing_the_others():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, result = call("compare_companies",
                                {"tickers": ["MMM", "ZZZ"], "metric": "revenue", "period": "2018"})
    assert not is_error
    assert result["results"]["MMM"]["passages"]
    assert "not in FinRAG's corpus" in result["results"]["ZZZ"]["error"]


def test_compare_needs_two_to_five_companies():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("compare_companies",
                              {"tickers": ["MMM"], "metric": "revenue", "period": "2018"})
    assert is_error and "2 to 5" in text


def test_latest_filing_links_to_sec_and_says_whether_it_is_searchable():
    filing = FilingMetadata(ticker="MMM", cik=66740, form_type="10-K", filing_date="2019-02-07",
                            accession_number="0000066740-19-000010", primary_document="mmm.htm")
    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker", return_value=66740),
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[filing]),
        tool_client(*ALL, deps=_deps()) as call,
    ):
        is_error, result = call("get_latest_filing", {"ticker": "MMM", "filing_type": "10-K"})
    assert not is_error
    assert result["sec_url"] == (
        "https://www.sec.gov/Archives/edgar/data/66740/000006674019000010/mmm.htm")
    assert result["in_corpus"] is True
    assert result["filing"]["filed"] == "2019-02-07"


def test_latest_filing_explains_an_unknown_ticker():
    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker",
              side_effect=ValueError("not found")),
        tool_client(*ALL, deps=_deps()) as call,
    ):
        is_error, text = call("get_latest_filing", {"ticker": "ZZZZ"})
    assert is_error and "SEC has no company with ticker ZZZZ" in text


def test_list_covered_companies_groups_filings_by_form():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, result = call("list_covered_companies", {})
    assert not is_error
    assert result["companies"][0] == {
        "ticker": "MMM",
        "forms": {"10-K": {"first": "2019-02-07", "last": "2019-02-07", "filings": 1}},
    }
    assert result["total_filings"] == 2


def test_verify_figures_reports_grounded_missing_and_unknown():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, result = call("verify_figures", {
            "answer": "3M spent $1,577 million, versus $1,999 million.",
            "passage_ids": ["a1", "gone"],
        })
    assert not is_error
    assert result["grounded"] == ["$1,577 million"]
    assert result["not_found"] == ["$1,999 million"]
    assert result["unknown_ids"] == ["gone"]


def test_a_crash_inside_a_tool_hides_its_details():
    class Exploding(FakeKeywordIndex):
        def coverage(self):
            raise RuntimeError("secret internals")

    deps = Deps(pinecone_returning([]), Exploding([CAPEX]), lambda t: [0.1], None)
    with tool_client(*ALL, deps=deps) as call:
        is_error, text = call("search_sec_filings", {"question": "capex", "ticker": "MMM"})
    assert is_error
    assert "secret" not in text


def test_latest_filing_looks_up_the_cik_once_per_ticker():
    from server.mcp_tools.get_latest_filing import _cik

    _cik.cache_clear()
    filing = FilingMetadata(ticker="MMM", cik=66740, form_type="10-K", filing_date="2019-02-07",
                            accession_number="0000066740-19-000010", primary_document="mmm.htm")
    with (
        patch("server.mcp_tools.get_latest_filing.get_cik_for_ticker",
              return_value=66740) as cik,
        patch("server.mcp_tools.get_latest_filing.list_filings", return_value=[filing]),
        tool_client(*ALL, deps=_deps()) as call,
    ):
        call("get_latest_filing", {"ticker": "MMM"})
        call("get_latest_filing", {"ticker": "MMM"})
    assert cik.call_count == 1


def test_compare_rejects_too_many_tickers():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("compare_companies", {"tickers": ["MMM"] * 11,
                                                    "metric": "revenue", "period": "2024"})
    assert is_error and "2 to 5" in text


def test_verify_rejects_too_many_ids_and_long_ids():
    with tool_client(*ALL, deps=_deps()) as call:
        many = call("verify_figures", {"answer": "x", "passage_ids": [f"i{n}" for n in range(21)]})
        long = call("verify_figures", {"answer": "x", "passage_ids": ["a" * 101]})
    assert many[0]
    assert long[0] and "too long" in long[1]


def test_huge_ticker_is_not_echoed_back():
    with tool_client(*ALL, deps=_deps()) as call:
        is_error, text = call("search_sec_filings", {"question": "q", "ticker": "A" * 5000})
    assert is_error and len(text) < 300


def test_verify_figures_does_not_log_the_answer_text():
    from unittest.mock import patch as p

    with p("server.mcp_tools.common.log_call") as log, tool_client(*ALL, deps=_deps()) as call:
        call("verify_figures", {"answer": "Capex was $1,577 million", "passage_ids": ["a1"]})
    args = log.call_args.kwargs["arguments"]
    assert "answer" not in args and args["answer_chars"] == 24

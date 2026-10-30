"""get_company_financials: passages for one metric, one company, one period."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from server.mcp_tools.common import (
    READ_ONLY,
    Deps,
    GetDeps,
    check_length,
    clean_ticker,
    passages_result,
    require_covered,
    run_tool,
)
from server.retrieval.evidence import find_passages
from server.retrieval.query_filters import extract_filters


def financials_passages(deps: Deps, ticker: str, metric: str, period: str) -> dict[str, Any]:
    """Passages for one company's metric; shared with compare_companies."""
    require_covered(ticker, deps.keyword_index)
    return passages_result(*find_passages(
        f"{ticker} {metric} {period}", deps.pinecone_index, deps.keyword_index, deps.embed_fn,
        ticker=ticker, years=extract_filters(period)["years"],
    ))


def register_get_financials_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register get_company_financials on an MCPServer."""

    @mcp.tool(title="Get company financials", annotations=READ_ONLY)
    def get_company_financials(ticker: str, metric: str, period: str) -> dict[str, Any]:
        """Find the passages that report one financial metric for a company and period.

        Returns source passages, not a number. Read the figure from them and cite it.

        Args:
            ticker: Company ticker, e.g. "MMM".
            metric: Metric name, e.g. "capital expenditure", "revenue", "gross margin".
            period: Reporting period, e.g. "FY2018", "2024", "Q1 FY2026".
        """
        symbol = clean_ticker(ticker)
        check_length("metric", metric, 100)
        check_length("period", period, 40)

        def work(deps):
            return {"ticker": symbol, "metric": metric, "period": period,
                    **financials_passages(deps, symbol, metric, period)}

        arguments = {"ticker": symbol, "metric": metric, "period": period}
        return run_tool(get_deps, "get_company_financials", arguments, work, cache=True)

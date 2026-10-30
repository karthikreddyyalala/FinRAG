"""compare_companies: the same reported figures across 2 to 5 companies, in parallel.

Parallel, not sequential: the old sequential loop through a throttled model
pushed comparisons past the 120 s Lambda timeout.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import GetDeps, check_length, clean_ticker, run_tool
from server.mcp_tools.get_financials import (
    MAX_METRICS,
    SEC_DATA,
    check_period,
    company_figures,
)


def register_compare_companies_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register compare_companies on an MCPServer."""

    @mcp.tool(title="Compare companies", annotations=SEC_DATA)
    def compare_companies(
        tickers: list[str], metrics: list[str], period: str = "latest"
    ) -> dict[str, Any]:
        """The same reported figures for several companies, side by side, from SEC XBRL data.

        Same figures and rules as get_company_financials. Each company uses its own
        fiscal year, so check period.end before comparing. A company SEC does not know
        gets an error entry; the others still return.

        Args:
            tickers: 2 to 5 tickers, e.g. ["TSLA", "F"].
            metrics: 1 to 10 metric names, e.g. ["revenue", "operating income"].
            period: "FY2024", "Q2 2025" or "latest" (default).
        """
        if len(tickers) > 10:  # 10 allows duplicates
            raise ToolError("Compare 2 to 5 companies.")
        symbols = list(dict.fromkeys(clean_ticker(t) for t in tickers))
        if not 2 <= len(symbols) <= 5:
            raise ToolError("Compare 2 to 5 companies.")
        if not 1 <= len(metrics) <= MAX_METRICS:
            raise ToolError(f"Pass 1 to {MAX_METRICS} metrics.")
        for m in metrics:
            check_length("metric", m, 100)
        check_period(period)

        def work(deps):
            def one(symbol):
                try:
                    return {"results": company_figures(symbol, metrics, period)}
                except ToolError as e:
                    return {"error": str(e)}

            with ThreadPoolExecutor(max_workers=len(symbols)) as pool:
                results = dict(zip(symbols, pool.map(one, symbols)))
            return {"period": period, "results": results}

        arguments = {"tickers": symbols, "metrics": metrics, "period": period}
        return run_tool(get_deps, "compare_companies", arguments, work, cache=True)

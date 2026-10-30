"""compare_companies: the same metric across 2 to 5 companies, looked up in parallel.

Parallel, not sequential: the old sequential loop through a throttled model
pushed comparisons past the 120 s Lambda timeout.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import READ_ONLY, GetDeps, check_length, clean_ticker, run_tool
from server.mcp_tools.get_financials import financials_passages


def register_compare_companies_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register compare_companies on an MCPServer."""

    @mcp.tool(title="Compare companies", annotations=READ_ONLY)
    def compare_companies(tickers: list[str], metric: str, period: str) -> dict[str, Any]:
        """Find passages reporting the same metric for several companies, side by side.

        Returns passages per company, or an error for a company FinRAG does not cover.

        Args:
            tickers: 2 to 5 tickers, e.g. ["TSLA", "F"].
            metric: Metric name, e.g. "revenue".
            period: Reporting period, e.g. "2024".
        """
        symbols = list(dict.fromkeys(clean_ticker(t) for t in tickers))
        if not 2 <= len(symbols) <= 5:
            raise ToolError("Compare 2 to 5 companies.")
        check_length("metric", metric, 100)
        check_length("period", period, 40)

        def work(deps):
            def one(symbol):
                try:
                    return financials_passages(deps, symbol, metric, period)
                except ToolError as e:
                    return {"error": str(e)}

            with ThreadPoolExecutor(max_workers=len(symbols)) as pool:
                results = dict(zip(symbols, pool.map(one, symbols)))
            return {"metric": metric, "period": period, "results": results}

        arguments = {"tickers": symbols, "metric": metric, "period": period}
        return run_tool(get_deps, "compare_companies", arguments, work, cache=True)

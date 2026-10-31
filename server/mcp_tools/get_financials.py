"""get_company_financials: exact reported figures for any US-listed company, from SEC XBRL."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from server.mcp_tools.common import GetDeps, check_length, clean_ticker, run_tool
from server.retrieval.xbrl_facts import FactsError, lookup, parse_period

MAX_METRICS = 10
# Calls SEC's data service, so open-world (unlike the corpus tools).
SEC_DATA = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def company_figures(ticker: str, metrics: list[str], period: str) -> list[dict[str, Any]]:
    """One result entry per metric; shared with compare_companies."""
    try:
        return [lookup(ticker, m, period) for m in metrics]
    except FactsError as e:
        raise ToolError(str(e)) from None


def check_period(period: str) -> None:
    check_length("period", period, 40)
    try:
        parse_period(period)
    except FactsError as e:
        raise ToolError(str(e)) from None


def register_get_financials_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register get_company_financials on an MCPServer."""

    @mcp.tool(title="Get company financials", annotations=SEC_DATA)
    def get_company_financials(
        ticker: str, metrics: list[str], period: str = "latest"
    ) -> dict[str, Any]:
        """Exact reported figures for any US-listed company, from the XBRL data in its filings.

        Each figure comes with its unit, period dates, source filing, link and citation.
        Use these numbers rather than reading tables when a question needs a reported
        figure; use search_sec_filings for explanations and context.

        Q4 is never filed on its own: a fourth-quarter figure is the one a 10-K tags, or
        full year minus nine months year-to-date, and then says so in "derived". A 10-Q
        cash flow figure may be year-to-date; "note" says so. Fiscal years are the
        company's own (Microsoft FY2024 ended June 2024).

        Args:
            ticker: Any ticker SEC knows, e.g. "MMM".
            metrics: 1 to 10 names, e.g. ["revenue", "cost of revenue", "net income"].
                Common names: revenue, net sales, cost of revenue, gross profit,
                operating income, net income, eps diluted, operating cash flow,
                capital expenditure, free cash flow, depreciation and amortization,
                total assets, current assets, total liabilities, current liabilities,
                cash, accounts receivable, inventory, accounts payable,
                property plant and equipment, long-term debt, shareholders equity,
                dividends paid, share repurchases. An XBRL concept such as
                "us-gaap:InterestExpense" also works; an unknown name returns
                suggestions from the company's own data.
            period: "FY2023", "2023", "Q3 2024", "Q4 FY2025", or "latest" (default).
        """
        symbol = clean_ticker(ticker)
        if not 1 <= len(metrics) <= MAX_METRICS:
            raise ToolError(f"Pass 1 to {MAX_METRICS} metrics.")
        for m in metrics:
            check_length("metric", m, 100)
        check_period(period)

        def work(deps):
            return {"ticker": symbol, "period": period,
                    "results": company_figures(symbol, metrics, period)}

        arguments = {"ticker": symbol, "metrics": metrics, "period": period}
        return run_tool(get_deps, "get_company_financials", arguments, work, cache=True)

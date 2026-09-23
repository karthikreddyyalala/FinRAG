"""compare_companies MCP tool: multi-hop lookup, one hop per ticker (Week 5).

Per CLAUDE.md Tool 3 spec: "multi-hop retrieval (separate query per company,
merged answer)". Reuses get_financials.build_financials_answer for the
per-company hop rather than reimplementing the lookup.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from server.mcp_tools.get_financials import build_financials_answer


def build_comparison_answer(
    tickers: list[str],
    metric: str,
    period: str,
    bedrock_client: Any,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
) -> dict[str, Any]:
    """Look up the same metric/period across several companies.

    A failure on one ticker (typo, uningested company) is captured per-company
    rather than aborting the whole comparison -- the other lookups already
    succeeded and there is no reason to discard them.

    Returns:
        {"metric", "period", "companies": [...], "latency_ms"}
        Each company entry is either a get_company_financials result or, on
        failure, {"ticker", "error"}.
    """
    start = time.monotonic()

    companies = []
    for ticker in tickers:
        try:
            companies.append(
                build_financials_answer(
                    ticker, metric, period,
                    bedrock_client=bedrock_client, pinecone_index=pinecone_index,
                    keyword_index=keyword_index, embed_fn=embed_fn,
                )
            )
        except Exception as e:
            companies.append({"ticker": ticker, "error": str(e)})

    return {
        "metric": metric,
        "period": period,
        "companies": companies,
        "latency_ms": int((time.monotonic() - start) * 1000),
    }


def register_compare_companies_tool(
    mcp: MCPServer,
    bedrock_client: Any,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
) -> None:
    """Register the compare_companies tool on an MCPServer instance."""

    @mcp.tool()
    def compare_companies(tickers: list[str], metric: str, period: str) -> dict[str, Any]:
        """Compare the same financial metric across several companies.

        Args:
            tickers: Company tickers to compare, e.g. ["TSLA", "F"].
            metric: Metric name, e.g. "gross margin".
            period: Reporting period, e.g. "2024-2025".

        Returns:
            Dict with metric, period, and a per-company list of results
            (or errors for tickers that failed to look up).
        """
        return build_comparison_answer(
            tickers, metric, period, bedrock_client, pinecone_index, keyword_index, embed_fn
        )

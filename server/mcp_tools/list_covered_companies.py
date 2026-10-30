"""list_covered_companies: which companies and filings FinRAG can search."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from server.mcp_tools.common import READ_ONLY, GetDeps, run_tool


def covered_companies(keyword_index: Any) -> dict[str, Any]:
    companies: dict[str, dict[str, dict[str, Any]]] = {}
    rows = keyword_index.coverage()
    for row in rows:
        forms = companies.setdefault(row["ticker"], {})
        form = forms.setdefault(row["filing_type"], {"first": row["filed"], "last": row["filed"],
                                                     "filings": 0})
        form["first"] = min(form["first"], row["filed"])
        form["last"] = max(form["last"], row["filed"])
        form["filings"] += 1
    return {
        "companies": [{"ticker": t, "forms": f} for t, f in sorted(companies.items())],
        "total_filings": len(rows),
    }


def register_list_covered_companies_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register list_covered_companies on an MCPServer."""

    @mcp.tool(title="List covered companies", annotations=READ_ONLY)
    def list_covered_companies() -> dict[str, Any]:
        """List the companies FinRAG covers, with each form type's date range and filing count.

        Call this first when unsure whether a company or year is covered.
        """
        return run_tool(get_deps, "list_covered_companies", {},
                        lambda deps: covered_companies(deps.keyword_index))

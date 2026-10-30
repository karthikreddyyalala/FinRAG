"""search_sec_filings: passages that answer a free-text financial question."""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from server.mcp_tools.common import (
    READ_ONLY,
    GetDeps,
    check_length,
    clean_ticker,
    passages_result,
    require_covered,
    run_tool,
)
from server.retrieval.evidence import find_passages

MAX_QUESTION_CHARS = 500


def register_search_filings_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register search_sec_filings on an MCPServer."""

    @mcp.tool(title="Search SEC filings", annotations=READ_ONLY)
    def search_sec_filings(
        question: str, ticker: str | None = None, fiscal_year: int | None = None
    ) -> dict[str, Any]:
        """Find passages in SEC filings (10-K, 10-Q, 8-K) that answer a financial question.

        Returns source passages, not an answer. Write the answer from them and
        cite each figure with its passage's citation.

        Args:
            question: The question in plain words, e.g. "3M capital expenditure in FY2018".
            ticker: Optional ticker to search one company only, e.g. "MMM".
            fiscal_year: Optional fiscal year, 1993 to 2100, e.g. 2018. Matches filings
                filed in that year or the next, since an annual report is filed after
                its year ends. If none match, passages from other years come back with
                a note saying so.
        """
        if not question.strip():
            raise ToolError("question is empty.")
        check_length("question", question, MAX_QUESTION_CHARS)
        symbol = clean_ticker(ticker) if ticker else None
        if fiscal_year is not None and not 1993 <= fiscal_year <= 2100:
            raise ToolError(f"fiscal_year {fiscal_year} is outside 1993 to 2100.")

        def work(deps):
            if symbol:
                require_covered(symbol, deps.keyword_index)
            years = (fiscal_year, fiscal_year) if fiscal_year else None
            return passages_result(*find_passages(
                question, deps.pinecone_index, deps.keyword_index, deps.embed_fn,
                ticker=symbol, years=years,
            ))

        arguments = {"question": question, "ticker": symbol, "fiscal_year": fiscal_year}
        return run_tool(get_deps, "search_sec_filings", arguments, work, cache=True)

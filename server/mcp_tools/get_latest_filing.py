"""get_latest_filing: a company's newest filing of a form type, live from EDGAR.

Works for any company SEC knows, not only the ones FinRAG has ingested;
in_corpus says whether the other tools can search that filing.
"""
from __future__ import annotations

import re
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from pipeline.edgar_client import ARCHIVE_URL, get_cik_for_ticker, list_filings
from server.mcp_tools.common import GetDeps, clean_ticker, run_tool

_FORM = re.compile(r"^[0-9A-Za-z][0-9A-Za-z\-/]{0,9}$")


def register_get_latest_filing_tool(mcp: MCPServer, get_deps: GetDeps) -> None:
    """Register get_latest_filing on an MCPServer."""

    @mcp.tool(
        title="Get latest filing",
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    def get_latest_filing(ticker: str, filing_type: str = "10-K") -> dict[str, Any]:
        """Get a company's most recent SEC filing of a given type, with a link to it on sec.gov.

        Args:
            ticker: Any ticker SEC knows, e.g. "AAPL".
            filing_type: SEC form, e.g. "10-K" (default), "10-Q", "8-K".
        """
        symbol = clean_ticker(ticker)
        if not _FORM.match(filing_type or ""):
            raise ToolError(f"{filing_type!r} is not an SEC form type, e.g. '10-K'.")
        form = filing_type.upper()

        def work(deps):
            try:
                cik = get_cik_for_ticker(symbol)
            except ValueError:
                raise ToolError(f"SEC has no company with ticker {symbol}.") from None
            filings = list_filings(symbol, cik, form_limits={form: 1})
            if not filings:
                raise ToolError(f"EDGAR lists no {form} filings for {symbol}.")
            f = filings[0]
            in_corpus = any(
                row["ticker"] == symbol and row["filing_type"] == form
                and row["filed"] == f.filing_date
                for row in deps.keyword_index.coverage()
            )
            return {
                "filing": {"ticker": symbol, "cik": f.cik, "form": f.form_type,
                           "filed": f.filing_date, "accession": f.accession_number,
                           "primary_document": f.primary_document},
                "sec_url": ARCHIVE_URL.format(
                    cik=f.cik, accession_no_dashes=f.accession_number.replace("-", ""),
                    primary_document=f.primary_document,
                ),
                "in_corpus": in_corpus,
            }

        # Not cached: EDGAR is the source of truth and a new filing can land any day.
        return run_tool(
            get_deps, "get_latest_filing", {"ticker": symbol, "filing_type": form}, work
        )

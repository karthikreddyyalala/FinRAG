"""FinRAG MCP server: FastAPI app for AWS Lambda behind a public Function URL.

Open to anyone with no sign-in. Constraints, each found by driving the app
through Mangum with real Function URL events:

- Stateless JSON responses: Lambda cannot hold a server-sent-events stream
  open or keep session state between invocations.
- A fresh app per invocation: the MCP session manager's run() may only be
  called once per instance, and Mangum runs the lifespan on every
  invocation. The expensive pieces live in get_dependencies().
- Dependencies load on the first tool call, not per request: initialize
  and tools/list never wait for the ~1 GB keyword index, which took about
  10.5 s of a cold request (61 cold starts measured, 2026-10).
- No chat model: tools return evidence and the client's model writes the
  answer, so no model quota can throttle or time out a request.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import boto3
from fastapi import FastAPI
from mangum import Mangum
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from pipeline.sync_pinecone import get_embed_fn, get_pinecone_index, load_keyword_index
from server.mcp_tools.common import Deps, GetDeps
from server.mcp_tools.compare_companies import register_compare_companies_tool
from server.mcp_tools.get_financials import register_get_financials_tool
from server.mcp_tools.get_latest_filing import register_get_latest_filing_tool
from server.mcp_tools.list_covered_companies import register_list_covered_companies_tool
from server.mcp_tools.search_filings import register_search_filings_tool
from server.mcp_tools.verify_figures import register_verify_figures_tool
from server.retrieval.evidence import find_passages
from server.ssm_secrets import SECRET_PARAMETERS as SECRET_PARAMETERS  # re-export
from server.ssm_secrets import load_secrets_from_ssm

PROCESSED_BUCKET = "finrag-processed-filings"
KEYWORD_INDEX_KEY = "keyword/index.sqlite"
# /tmp is the only writable path on Lambda and persists across warm invocations.
KEYWORD_INDEX_LOCAL_PATH = "/tmp/finrag/keyword.sqlite"
SITE_URL = "https://dashboard-weld-nine-28.vercel.app"
HEALTH_CHECK = {"question": "3M capital expenditure FY2018", "ticker": "MMM",
                "years": (2018, 2018)}

INSTRUCTIONS = """\
FinRAG answers questions about US public companies from their SEC filings, with sources.

For a reported figure (revenue, net income, capex, total assets, EPS, ...), call \
get_company_financials. It works for any company SEC knows and returns the exact value \
from the filing's XBRL data, with its period, source filing, link and citation. Pass every \
figure a calculation needs in one call, e.g. ["revenue", "cost of revenue"] for gross \
margin, then compute the ratio yourself and show its inputs. compare_companies does the same \
for 2 to 5 companies.

For explanations, risks, guidance, segment detail and anything else written in the filing, \
call search_sec_filings. It searches the full text of the 10-K, 10-Q and 8-K filings of 71 \
large companies (list_covered_companies lists them) and returns cited passages.

Write the answer yourself:
- Cite every figure, e.g. [MMM 10-K 2019-02-07].
- Never state a number that no tool returned. If the tools lack it, say so.
- A fourth quarter is never filed on its own; get_company_financials says when Q4 is derived \
as full year minus nine months. Fiscal years are the company's own (Walmart FY2026 ended \
January 2026).
- In passages, a number in parentheses is negative or a cash outflow: (1,577) spent means \
1,577 spent.

Before a final answer that contains figures, call verify_figures with your draft and the ids \
of the passages and figures you used (figure ids start with "xbrl:"), then fix or flag \
anything listed in not_found. get_latest_filing links any company's newest filing on \
sec.gov. Stock prices and news are not in SEC filings."""

REGISTERS = (
    register_search_filings_tool, register_get_financials_tool, register_compare_companies_tool,
    register_get_latest_filing_tool, register_list_covered_companies_tool,
    register_verify_figures_tool,
)


def create_app(get_deps: GetDeps) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted at /mcp.

    Args:
        get_deps: Returns the tools' dependencies; called on the first tool
            call, never for initialize or tools/list.
    """
    mcp = MCPServer(
        "FinRAG", title="FinRAG: SEC filings evidence", instructions=INSTRUCTIONS,
        website_url=SITE_URL,
    )
    for register in REGISTERS:
        register(mcp, get_deps)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount(
        "/",
        mcp.streamable_http_app(
            json_response=True,
            stateless_http=True,
            # The guard admits only localhost Host headers, protecting servers
            # bound to localhost from malicious web pages. This is a public
            # HTTPS endpoint; with the guard on, every Lambda URL request is 421.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        ),
    )
    return app


def _build_production_dependencies() -> Deps:
    """Pinecone, the keyword index, the query embedder, DynamoDB.

    Expects secrets already in the environment (the handler loads them).
    """
    return Deps(
        pinecone_index=get_pinecone_index(
            api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
        ),
        keyword_index=load_keyword_index(
            boto3.client("s3"), PROCESSED_BUCKET, KEYWORD_INDEX_KEY, KEYWORD_INDEX_LOCAL_PATH
        ),
        # Must be the corpus's model (OpenAI text-embedding-3-small): querying
        # Pinecone with another model's vectors returns unrelated chunks silently.
        embed_fn=get_embed_fn(),
        dynamodb=boto3.resource("dynamodb"),
    )


@lru_cache(maxsize=1)
def get_dependencies() -> Deps:
    """Build the expensive dependencies once per Lambda instance."""
    return _build_production_dependencies()


def run_health_check(deps: Deps) -> dict[str, Any]:
    """One real retrieval: embedding, Pinecone, keyword index, full-text lookup.

    EventBridge invokes this every 5 minutes. Raising makes the invocation an
    error, which the alarm counts, so an expired key or an empty OpenAI
    balance (2026-10-24, 2026-10-28) surfaces within minutes instead of in
    front of a visitor. The schedule also keeps one instance warm.
    """
    # Candidates only: reranking every 5 minutes cost ~9.5M Voyage tokens a day.
    chunks, note = find_passages(
        HEALTH_CHECK["question"], deps.pinecone_index, deps.keyword_index, deps.embed_fn,
        ticker=HEALTH_CHECK["ticker"], years=HEALTH_CHECK["years"], stage="candidates",
    )
    if note or not chunks:
        raise RuntimeError(f"health check failed: {len(chunks)} passages, note={note!r}")
    return {"ok": True, "passages": len(chunks)}


def handler(event: Any, context: Any) -> Any:
    """Lambda entry point: the scheduled health check, or an MCP request."""
    load_secrets_from_ssm(
        boto3.client("ssm"), prefix=os.environ.get("FINRAG_SSM_PREFIX", "/finrag")
    )
    if event.get("finrag_health_check"):
        return run_health_check(get_dependencies())
    return Mangum(create_app(get_dependencies), lifespan="auto")(event, context)

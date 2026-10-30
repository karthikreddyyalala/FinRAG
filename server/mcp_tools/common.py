"""Shared plumbing for the MCP tools: dependencies, input checks, run_tool."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from server.observability.call_log import log_call
from server.observability.tool_cache import get_cached, put_cached
from server.rate_limit import RateLimited, check_rate_limit
from server.retrieval.evidence import to_passage

QUERY_LOG_TABLE = "finrag-query-logs"
QUERY_CACHE_TABLE = "finrag-query-cache"
# Reads only our own corpus; get_latest_filing overrides openWorldHint (EDGAR).
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_TICKER = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,5}$")


@dataclass(frozen=True)
class Deps:
    """What the tools need. Built once per Lambda instance, on the first tool call."""

    pinecone_index: Any
    keyword_index: Any
    embed_fn: Callable[[str], list[float]]
    dynamodb: Any = None


GetDeps = Callable[[], Deps]


def clean_ticker(ticker: str) -> str:
    """Upper-cased ticker, or a ToolError the model can act on."""
    if not _TICKER.match(ticker or ""):
        raise ToolError(f"{ticker!r} is not a ticker symbol, e.g. 'MMM' or 'BRK.B'.")
    return ticker.upper()


def check_length(name: str, value: str, limit: int) -> None:
    if len(value) > limit:
        raise ToolError(f"{name} is {len(value)} characters; the limit is {limit}.")


def require_covered(ticker: str, keyword_index: Any) -> None:
    covered = {row["ticker"] for row in keyword_index.coverage()}
    if ticker not in covered:
        raise ToolError(
            f"{ticker} is not in FinRAG's corpus ({len(covered)} companies). "
            "Call list_covered_companies for the list."
        )


def passages_result(chunks: list[dict[str, Any]], note: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"passages": [to_passage(c) for c in chunks]}
    if note:
        result["note"] = note
    return result


def run_tool(
    get_deps: GetDeps,
    tool: str,
    arguments: dict[str, Any],
    work: Callable[[Deps], dict[str, Any]],
    cache: bool = False,
) -> dict[str, Any]:
    """One tool call: shared limit, cache, the work itself, one log record.

    A ToolError's message reaches the model as-is. Any other exception
    reaches it only as "Error executing tool NAME" (the SDK hides crash
    details); the log record keeps the real error.
    """
    start = time.monotonic()
    deps = get_deps()
    state: dict[str, Any] = {"cache_hit": False, "rate_limited": False, "error": None,
                             "result": None}
    try:
        if deps.dynamodb is not None:
            check_rate_limit(deps.dynamodb)
        use_cache = cache and deps.dynamodb is not None
        result = (
            get_cached(deps.dynamodb, QUERY_CACHE_TABLE, tool, arguments) if use_cache else None
        )
        if result is not None:
            state["cache_hit"] = True
        else:
            result = work(deps)
            if use_cache:
                put_cached(deps.dynamodb, QUERY_CACHE_TABLE, tool, arguments, result)
        state["result"] = result
        return result
    except RateLimited as e:
        state["rate_limited"] = True
        raise ToolError(
            f"FinRAG is at its shared usage limit. Try again in {e.retry_after} seconds."
        ) from None
    except Exception as e:
        state["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        log_call(
            deps.dynamodb, QUERY_LOG_TABLE, tool=tool, arguments=arguments,
            latency_ms=int((time.monotonic() - start) * 1000), result=state["result"],
            cache_hit=state["cache_hit"], rate_limited=state["rate_limited"],
            error=state["error"],
        )

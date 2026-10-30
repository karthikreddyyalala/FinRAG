"""One record per MCP tool call: a DynamoDB row plus one CloudWatch line.

The CloudWatch line ("finrag_call {json}") is what Logs Insights queries;
the DynamoDB row (finrag-query-logs) keeps history past log retention.
Best effort: logging never fails a call.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

MAX_ARGUMENT_CHARS = 500


def log_call(
    dynamodb_resource: Any,
    table_name: str,
    *,
    tool: str,
    arguments: dict[str, Any],
    latency_ms: int,
    result: dict[str, Any] | None,
    cache_hit: bool = False,
    rate_limited: bool = False,
    error: str | None = None,
) -> None:
    """Record one tool call. Never raises."""
    passages = _passages(result)
    record = {
        "tool": tool,
        "arguments": json.dumps(arguments, default=str)[:MAX_ARGUMENT_CHARS],
        "latency_ms": latency_ms,
        "n_passages": len(passages),
        "tickers": sorted({p["ticker"] for p in passages if p.get("ticker")}),
        "cache_hit": cache_hit,
        "rate_limited": rate_limited,
        "error": error,
    }
    print("finrag_call " + json.dumps(record), flush=True)
    if dynamodb_resource is None:
        return
    try:
        dynamodb_resource.Table(table_name).put_item(Item={
            "query_id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **{k: v for k, v in record.items() if v is not None},
        })
    except Exception:
        pass


def _passages(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Passages in a single result, or across compare_companies' per-ticker results."""
    if not result:
        return []
    found = list(result.get("passages", []))
    for value in (result.get("results") or {}).values():
        found.extend(value.get("passages", []))
    return found

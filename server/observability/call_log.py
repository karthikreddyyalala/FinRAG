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
    figures = _figures(result)
    record = {
        "tool": tool,
        "arguments": json.dumps(arguments, default=str)[:MAX_ARGUMENT_CHARS],
        "latency_ms": latency_ms,
        "n_passages": len(passages),
        "n_figures": sum(len(f) for f in figures.values()),
        "tickers": sorted({p["ticker"] for p in passages if p.get("ticker")}
                          | {t for t, f in figures.items() if f}),
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
            "expires_at": int(time.time()) + 90 * 24 * 3600,  # DynamoDB TTL
            **{k: v for k, v in record.items() if v is not None},
        })
    except Exception:
        pass


def _passages(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Passages in a search result. Figure results (get_company_financials) hold none."""
    if not result:
        return []
    return list(result.get("passages", []))


def _figures(result: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Figures found per ticker: get_company_financials' list or compare_companies' dict."""
    if not result:
        return {}
    entries = result.get("results")
    if isinstance(entries, list):
        return {result.get("ticker", ""): [e for e in entries if "value" in e]}
    if isinstance(entries, dict):
        return {t: [e for e in (v.get("results") or []) if "value" in e]
                for t, v in entries.items()}
    return {}

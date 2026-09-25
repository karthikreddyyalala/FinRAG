"""Query result cache in DynamoDB (Phase C4, CLAUDE.md).

Caches search_sec_filings' final answer, keyed by a hash of the normalized
question text. Scoped to that one tool deliberately: get_company_financials
and compare_companies take structured (ticker, metric, period) args, not
free text -- a different cache-key shape -- and are lower-value here since
C5's model-tier routing targets those two next.

TTL is fixed at 24 hours, not tied to the weekly EventBridge corpus refresh
(scripts/weekly_refresh.py). A longer TTL (e.g. 7 days) would save more, but
a query cached Monday could then serve a stale answer if Wednesday's refresh
adds a newer filing for that exact ticker before the entry expires. 24h means
a cached answer can never survive into a week where the corpus changed.
"""
from __future__ import annotations

import hashlib
import re
import time
from decimal import Decimal
from typing import Any

CACHE_TTL_SECONDS = 24 * 60 * 60


def normalize_query(query: str) -> str:
    """Fold whitespace/case differences so equivalent questions share a
    cache key ("Nvidia  revenue?" and "nvidia revenue?" -> same hash)."""
    return re.sub(r"\s+", " ", query.strip().lower())


def cache_key(query: str) -> str:
    """sha256 hex digest of the normalized query, used as the DynamoDB
    partition key. Hashed (not the raw query) so an arbitrarily long
    question never risks DynamoDB's key-length limit."""
    return hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()


def get_cached_answer(dynamodb_resource: Any, table_name: str, query: str) -> dict[str, Any] | None:
    """Look up a cached {"answer", "citations"} payload for this query.

    Best-effort: any failure (throttled table, network blip, IAM
    misconfig, missing table) returns None (a cache miss) rather than
    raising -- a cache outage must never fail the user's actual query.
    Also treats an item past its own recorded expiry as a miss, as a
    second check independent of DynamoDB's TTL sweep, which is
    best-effort and can lag real time by minutes.
    """
    try:
        table = dynamodb_resource.Table(table_name)
        response = table.get_item(Key={"query_hash": cache_key(query)})
        item = response.get("Item")
        if item is None:
            return None
        if int(item.get("ttl", 0)) < int(time.time()):
            return None
        return {"answer": item["answer"], "citations": item["citations"]}
    except Exception:
        return None


def put_cached_answer(
    dynamodb_resource: Any, table_name: str, query: str, answer: str, citations: list[dict[str, Any]]
) -> None:
    """Write this query's answer to the cache with a 24h TTL.

    Best-effort, same rationale as get_cached_answer / logger.log_query:
    never raises, a caching failure must not fail the user's actual query.
    """
    try:
        table = dynamodb_resource.Table(table_name)
        table.put_item(Item={
            "query_hash": cache_key(query),
            "query": query,
            "answer": answer,
            "citations": _to_dynamodb_safe(citations),
            "cached_at": int(time.time()),
            "ttl": int(time.time()) + CACHE_TTL_SECONDS,
        })
    except Exception:
        pass


def _to_dynamodb_safe(value: Any) -> Any:
    """DynamoDB's resource API rejects native float; citations carry no
    floats today, but recurse so a future field doesn't silently break
    this the way logger.py's _to_decimal exists for cost_usd."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamodb_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb_safe(v) for v in value]
    return value

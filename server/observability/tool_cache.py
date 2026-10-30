"""24-hour cache of MCP tool results in DynamoDB (table finrag-query-cache).

Keyed by tool name + arguments + a hash of the server's source, so a deploy
that changes ranking never serves results from the previous build. TTL is
24 hours, not a week: the weekly corpus refresh may add a filing for exactly
the company a cached result is about, and 24 hours means a cached result
never survives into a week where the corpus changed. Best effort throughout: a cache fault is a miss, never
an error.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

CACHE_TTL_SECONDS = 24 * 60 * 60
# v1 entries held generated answers (the pre-M1 pipeline); never read them back.
KEY_VERSION = "v2"
# Changes with any edit under server/; computed once per cold start (~60 small files).
CODE_VERSION = hashlib.sha256(b"".join(
    p.read_bytes() for p in sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
)).hexdigest()[:12]


def cache_key(tool: str, arguments: dict[str, Any]) -> str:
    """sha256 of the normalized (versions, tool, arguments): case and spacing fold."""
    text = json.dumps([KEY_VERSION, CODE_VERSION, tool, arguments], sort_keys=True, default=str)
    return hashlib.sha256(re.sub(r"\s+", " ", text.lower()).encode("utf-8")).hexdigest()


def get_cached(
    dynamodb_resource: Any, table_name: str, tool: str, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    """The cached result, or None on a miss, an expired entry, or any fault."""
    try:
        item = dynamodb_resource.Table(table_name).get_item(
            Key={"query_hash": cache_key(tool, arguments)}
        ).get("Item")
        # DynamoDB's TTL sweep can lag by minutes; check the expiry ourselves too.
        if item is None or int(item.get("ttl", 0)) < int(time.time()):
            return None
        return _from_dynamodb(item["payload"])
    except Exception:
        return None


def put_cached(
    dynamodb_resource: Any, table_name: str, tool: str, arguments: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    """Store a result for 24 hours. Never raises."""
    try:
        now = int(time.time())
        dynamodb_resource.Table(table_name).put_item(Item={
            "query_hash": cache_key(tool, arguments),
            "tool": tool,
            "payload": _to_dynamodb(payload),
            "cached_at": now,
            "ttl": now + CACHE_TTL_SECONDS,
        })
    except Exception:
        pass


def _to_dynamodb(value: Any) -> Any:
    """DynamoDB's resource API rejects native float."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamodb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb(v) for v in value]
    return value


def _from_dynamodb(value: Any) -> Any:
    """Numbers come back as Decimal; the MCP client should see plain ints/floats."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamodb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb(v) for v in value]
    return value
